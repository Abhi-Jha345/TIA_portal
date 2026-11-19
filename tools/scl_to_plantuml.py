"""Generate a UML class diagram (PlantUML) from the SCL sources.

The diagram is derived from the code, so it cannot drift away from it:
  * FB / FC        -> class with stereotype <<FB>> / <<FC>>, interface grouped as
                      in / out / in-out / static (multi-instances shown as composition)
  * UDT            -> class <<UDT>>
  * global DB      -> class <<DB>>
  * multi-instance -> composition  (FB *-- FB : instance name)
  * FC call        -> dependency   (FB ..> FC : calls)
  * UDT usage      -> dependency   (X ..> UDT)
  * block version  -> shown in the class title (v1.0)

Usage: python tools/scl_to_plantuml.py  [output.puml]
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
from scl_runtime import Parser, tokenize   # noqa: E402  (same parser as the unit tests)
import block_versions                      # noqa: E402

SOURCES = ["01_Types.scl", "02_Blocks.scl", "03_OB.scl"]
SYSTEM_FBS = {"TON_TIME", "TON", "R_TRIG", "F_TRIG"}
SECTION_SYMBOL = {"input": "+ in ", "output": "+ out ", "inout": "+ inout ", "static": "- "}


PRIM = {"BOOL": "Bool", "INT": "Int", "DINT": "DInt", "REAL": "Real", "TIME": "Time",
        "WORD": "Word", "STRING": "String", "BYTE": "Byte", "DWORD": "DWord"}
ORIGINAL = {}          # lower-case name -> spelling used in the source


def type_name(t):
    kind, info = t
    if kind == "named":
        return info
    if kind == "struct":
        return "Struct"
    return PRIM.get(info, info)


def orig(name):
    return ORIGINAL.get(name.lower(), name)


def collect():
    blocks = []
    for f in SOURCES:
        text = (ROOT / "src" / f).read_text(encoding="utf-8")
        code = re.sub(r"'[^']*'", "", re.sub(r"//[^\n]*", "", text))   # no comments, no strings
        for word in re.findall(r"^\s*([A-Za-z_]\w*)\s*:", code, re.MULTILINE):  # declarations first
            ORIGINAL.setdefault(word.lower(), word)
        for word in re.findall(r"\b[A-Za-z_]\w*\b", code):
            ORIGINAL.setdefault(word.lower(), word)
        blocks += Parser(tokenize(text), filename=f).parse_unit()
    return blocks


def globals_in(body, dbs):
    """Names of global data blocks referenced in a statement list."""
    return {n[1] for n in _walk(body)
            if isinstance(n, tuple) and len(n) == 2 and n[0] == "global" and n[1] in dbs}


def calls_in(body, found):
    """Collect names of global FCs called anywhere in a statement list."""
    for node in _walk(body):
        if isinstance(node, tuple) and node and node[0] == "fcall" and node[1][0] == "global":
            found.add(node[1][1])
    return found


def _walk(obj):
    if isinstance(obj, (list, tuple)):
        yield obj
        for item in obj:
            yield from _walk(item)


def render(blocks):
    versions = {n: block_versions.fmt(b["version"]) for n, b in block_versions.parse_blocks().items()}
    names = {b.name for b in blocks}
    global_dbs = {b.name for b in blocks if b.kind == "DATA_BLOCK" and not b.instance_of}
    out = ["@startuml scl_class_diagram",
           "!pragma layout smetana",
           "title Battery cell sorting station - block structure (generated from src/*.scl)",
           "skinparam classAttributeIconSize 0",
           "skinparam class {",
           "  BackgroundColor<<FB>> #E8F3F6",
           "  BackgroundColor<<FC>> #F3F0FA",
           "  BackgroundColor<<UDT>> #FDF6E3",
           "  BackgroundColor<<DB>> #EEF5EA",
           "  BackgroundColor<<OB>> #FBEAEA",
           "}",
           "hide empty methods", ""]
    relations = []
    for b in blocks:
        stereo = {"FUNCTION_BLOCK": "FB", "FUNCTION": "FC", "TYPE": "UDT",
                  "ORGANIZATION_BLOCK": "OB", "DATA_BLOCK": "DB"}[b.kind]
        if b.kind == "DATA_BLOCK" and b.instance_of:
            relations.append(f'"{b.name}" ..> "{b.instance_of}" : instance DB of')
            out.append(f'class "{b.name}" <<DB>> {{\n  instance of {b.instance_of}\n}}')
            continue
        title = f'class "{b.name}" as {_alias(b.name)} <<{stereo}>>'
        out.append(f'{title} {{')
        out.append(f'  .. v{versions.get(b.name, "?")} ..')
        if b.ret_type:
            out.append(f"  + return : {type_name(b.ret_type)}")
        for section in ("input", "output", "inout", "static"):
            for name, t, _init in b.sections.get(section, []):
                tn = type_name(t)
                if t[0] == "named" and t[1] in names and b.kind != "TYPE":
                    if t[1].startswith("FB_"):
                        relations.append(f'{_alias(b.name)} *-- {_alias(t[1])} : {orig(name)}')
                        continue
                    relations.append(f'{_alias(b.name)} ..> {_alias(t[1])}')
                if tn in SYSTEM_FBS:
                    continue                      # timers / edges: implementation detail
                symbol = "+ " if b.kind in ("TYPE", "DATA_BLOCK") else SECTION_SYMBOL[section]
                out.append(f"  {symbol}{orig(name)} : {tn}")
        out.append("}")
        for fc in sorted(calls_in(b.body, set())):
            relations.append(f'{_alias(b.name)} ..> {_alias(fc)} : calls')
        for db in sorted(globals_in(b.body, global_dbs)):
            relations.append(f'{_alias(b.name)} ..> {_alias(db)} : reads / writes')
        for call in _instance_calls(b):
            relations.append(call)
    out.append("")
    out += sorted(set(relations))
    out.append("@enduml")
    return "\n".join(out) + "\n"


def _instance_calls(block):
    """OB -> global instance DB calls."""
    res = []
    for node in _walk(block.body):
        if isinstance(node, tuple) and node and node[0] == "call" and node[1][0] == "global":
            res.append(f'{_alias(block.name)} --> "{node[1][1]}" : calls every cycle')
    return res


def _alias(name):
    return re.sub(r"\W", "_", name)


def main(argv):
    target = pathlib.Path(argv[1]) if len(argv) > 1 else ROOT / "docs" / "uml" / "01_class_blocks.puml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(collect()), encoding="utf-8")
    print(f"written {target}")


if __name__ == "__main__":
    main(sys.argv)
