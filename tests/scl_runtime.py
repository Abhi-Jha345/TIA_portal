"""Minimal SCL runtime for unit tests without PLCSIM.

Parses the *same* .scl external sources that are imported into TIA Portal and executes
them scan by scan with a simulated clock. It supports the subset of SCL used in this
project: TYPE / FUNCTION / FUNCTION_BLOCK / DATA_BLOCK / ORGANIZATION_BLOCK, IF/ELSIF/ELSE,
CASE, REGION, assignments, FB and FC calls with named parameters, IEC TON_TIME / R_TRIG /
F_TRIG, structs and UDTs, Bool/Int/DInt/Real/Time/Word/String.

It is a test tool, not a PLC: no cycle-time effects, no retentivity, no overflow checks.
Anything it does not understand raises SclError instead of guessing.
"""
import copy
import re


class SclError(Exception):
    pass


# --------------------------------------------------------------------------- tokens
_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|\(\*.*?\*\))
  | (?P<attr>\{[^}]*\})
  | (?P<time>T\#[0-9A-Za-z_.]+)
  | (?P<hex>16\#[0-9A-Fa-f_]+)
  | (?P<real>\d+\.\d+(?:[eE][+-]?\d+)?)
  | (?P<int>\d+)
  | (?P<string>'(?:[^']|'')*')
  | (?P<qid>"[^"]+")
  | (?P<lid>\#[A-Za-z_]\w*)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<op>:=|=>|<>|>=|<=|\.\.|\*\*|[;:,.()\[\]=<>+\-*/&])
""", re.VERBOSE | re.DOTALL)


def _parse_time(text):
    body = text[2:].upper().replace("_", "")
    total = 0.0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(MS|S|M|H|D)", body):
        total += float(num) * {"MS": 1, "S": 1000, "M": 60000, "H": 3600000, "D": 86400000}[unit]
    if total == 0 and not re.fullmatch(r"0+(MS|S|M|H|D)?", body):
        raise SclError(f"cannot parse time literal {text}")
    return int(total)


# Decision coverage of the SCL source: every IF branch (incl. implicit ELSE) and every CASE
# label (incl. implicit ELSE) is registered at parse time and marked when executed.
COVERAGE = {"points": {}, "hit": set()}


def _register(key, label):
    COVERAGE["points"][key] = label


def tokenize(src):
    toks, pos, line = [], 0, 1
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise SclError(f"unexpected character {src[pos]!r} at offset {pos}")
        kind, text = m.lastgroup, m.group()
        pos = m.end()
        start_line = line
        line += text.count("\n")
        if kind in ("ws", "comment", "attr"):
            continue
        if kind == "id" and text.upper() in ("IF", "CASE"):
            toks.append(("id", text.upper(), start_line))
            continue
        if kind == "time":
            toks.append(("lit", _parse_time(text)))
        elif kind == "hex":
            toks.append(("lit", int(text[3:].replace("_", ""), 16)))
        elif kind == "real":
            toks.append(("lit", float(text)))
        elif kind == "int":
            toks.append(("lit", int(text)))
        elif kind == "string":
            toks.append(("lit", text[1:-1].replace("''", "'")))
        elif kind == "qid":
            toks.append(("qid", text[1:-1]))
        elif kind == "lid":
            toks.append(("lid", text[1:].lower()))
        elif kind == "id":
            up = text.upper()
            if up == "TRUE":
                toks.append(("lit", True))
            elif up == "FALSE":
                toks.append(("lit", False))
            else:
                toks.append(("id", up))
        else:
            toks.append(("op", text))
    toks.append(("eof", None))
    return toks


# --------------------------------------------------------------------------- values
class Obj:
    """Struct / UDT / FB instance. Member names are case-insensitive like in SCL."""

    def __init__(self, typename=""):
        object.__setattr__(self, "_v", {})
        object.__setattr__(self, "_type", typename)

    def __getattr__(self, name):
        v = object.__getattribute__(self, "_v")
        key = name.lower()
        if key not in v:
            raise AttributeError(f"{object.__getattribute__(self, '_type')} has no member {name}")
        return v[key]

    def __setattr__(self, name, value):
        v = object.__getattribute__(self, "_v")
        key = name.lower()
        if key not in v:
            raise AttributeError(f"{object.__getattribute__(self, '_type')} has no member {name}")
        v[key] = value

    def has(self, name):
        return name.lower() in object.__getattribute__(self, "_v")

    def define(self, name, value):
        object.__getattribute__(self, "_v")[name.lower()] = value

    def __repr__(self):
        return f"<{object.__getattribute__(self, '_type')} {object.__getattribute__(self, '_v')}>"


class Ton(Obj):
    def __init__(self):
        super().__init__("TON_TIME")
        for k, v in (("in", False), ("pt", 0), ("q", False), ("et", 0)):
            self.define(k, v)
        object.__setattr__(self, "_start", None)

    def execute(self, now):
        if self.IN:
            if object.__getattribute__(self, "_start") is None:
                object.__setattr__(self, "_start", now)
            et = now - object.__getattribute__(self, "_start")
            self.ET = min(et, self.PT)
            self.Q = et >= self.PT
        else:
            object.__setattr__(self, "_start", None)
            self.ET = 0
            self.Q = False


class Trig(Obj):
    def __init__(self, rising):
        super().__init__("R_TRIG" if rising else "F_TRIG")
        for k, v in (("clk", False), ("q", False), ("m", False)):
            self.define(k, v)
        object.__setattr__(self, "_rising", rising)

    def execute(self, now):
        if object.__getattribute__(self, "_rising"):
            self.Q = self.CLK and not self.M
        else:
            self.Q = (not self.CLK) and self.M
        self.M = self.CLK


_PRIM_DEFAULT = {"BOOL": False, "INT": 0, "DINT": 0, "SINT": 0, "UINT": 0, "UDINT": 0,
                 "BYTE": 0, "WORD": 0, "DWORD": 0, "REAL": 0.0, "LREAL": 0.0, "TIME": 0,
                 "STRING": ""}


# --------------------------------------------------------------------------- parser
class Block:
    def __init__(self, kind, name):
        self.kind, self.name = kind, name
        self.sections = {}           # section -> list of (name, type, init)
        self.ret_type = None
        self.body = []
        self.instance_of = None      # for instance DBs


class Parser:
    SECTIONS = {"VAR_INPUT": "input", "VAR_OUTPUT": "output", "VAR_IN_OUT": "inout",
                "VAR_TEMP": "temp", "VAR": "static"}

    def __init__(self, toks, filename=""):
        self.t, self.i = toks, 0
        self.filename = filename
        self.block = ""

    # helpers
    def peek(self, k=0):
        tok = self.t[self.i + k]
        return tok[:2]

    def line(self):
        tok = self.t[self.i]
        return tok[2] if len(tok) > 2 else 0

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok[:2]

    def accept(self, kind, val=None):
        tok = self.peek()
        if tok[0] == kind and (val is None or tok[1] == val):
            self.i += 1
            return tok
        return None

    def expect(self, kind, val=None):
        tok = self.accept(kind, val)
        if not tok:
            raise SclError(f"expected {kind} {val or ''}, got {self.peek()} (token {self.i})")
        return tok

    def is_id(self, *vals):
        tok = self.peek()
        return tok[0] == "id" and tok[1] in vals

    # top level
    def parse_unit(self):
        blocks = []
        while self.peek()[0] != "eof":
            kw = self.expect("id")[1]
            if kw == "TYPE":
                blocks.append(self.parse_type())
            elif kw in ("FUNCTION", "FUNCTION_BLOCK", "ORGANIZATION_BLOCK", "DATA_BLOCK"):
                blocks.append(self.parse_block(kw))
            else:
                raise SclError(f"unexpected top-level keyword {kw}")
        return blocks

    def skip_header(self):
        while True:
            if self.accept("id", "VERSION"):
                self.expect("op", ":")
                self.next()
            elif self.accept("id", "TITLE"):
                self.expect("op", "=")
                self.next()
            elif self.accept("id", "NON_RETAIN"):
                pass
            else:
                return

    def parse_type(self):
        b = Block("TYPE", self.expect("qid")[1])
        self.skip_header()
        b.sections["static"] = self.parse_type_spec()[1]
        self.accept("op", ";")
        self.expect("id", "END_TYPE")
        return b

    def parse_block(self, kw):
        b = Block(kw, self.expect("qid")[1])
        self.block = b.name
        if kw == "FUNCTION":
            self.expect("op", ":")
            b.ret_type = self.parse_type_spec()
        self.skip_header()
        if kw == "DATA_BLOCK" and self.peek()[0] == "qid":
            b.instance_of = self.next()[1]
        while True:
            tok = self.peek()
            if tok[0] == "id" and tok[1].startswith("VAR"):
                self.parse_var_section(b)
            else:
                break
        self.expect("id", "BEGIN")
        end = "END_" + kw
        b.body = self.parse_stmts((end,))
        self.expect("id", end)
        return b

    def parse_var_section(self, b):
        kw = self.next()[1]
        if kw == "VAR" and self.accept("id", "CONSTANT"):
            section = "constant"
        else:
            section = self.SECTIONS.get(kw)
            if section is None:
                raise SclError(f"unsupported section {kw}")
        decls = b.sections.setdefault(section, [])
        while not self.accept("id", "END_VAR"):
            decls.append(self.parse_decl())

    def parse_decl(self):
        name = self.expect("id")[1].lower()
        self.expect("op", ":")
        typ = self.parse_type_spec()
        init = None
        if self.accept("op", ":="):
            init = self.parse_expr()
        self.expect("op", ";")
        return (name, typ, init)

    def parse_type_spec(self):
        tok = self.next()
        if tok[0] == "qid":
            return ("named", tok[1])
        if tok[0] != "id":
            raise SclError(f"bad type {tok}")
        if tok[1] == "STRUCT":
            members = []
            while not self.accept("id", "END_STRUCT"):
                members.append(self.parse_decl())
            return ("struct", members)
        if tok[1] == "STRING" and self.accept("op", "["):
            self.next()
            self.expect("op", "]")
            return ("prim", "STRING")
        return ("prim", tok[1])

    # statements
    def parse_stmts(self, terminators):
        stmts = []
        while not (self.peek()[0] == "id" and self.peek()[1] in terminators):
            if self.peek()[0] == "eof":
                raise SclError(f"unexpected end of source, missing {terminators}")
            s = self.parse_stmt()
            if s is not None:
                stmts.append(s)
        return stmts

    def parse_stmt(self):
        tok = self.peek()
        if tok == ("op", ";"):
            self.next()
            return None
        if tok[0] == "id":
            if tok[1] == "IF":
                return self.parse_if()
            if tok[1] == "CASE":
                return self.parse_case()
            if tok[1] == "REGION":
                self.next()
                self.expect("id")
                body = self.parse_stmts(("END_REGION",))
                self.expect("id", "END_REGION")
                return ("block", body)
        target = self.parse_designator()
        if self.accept("op", ":="):
            expr = self.parse_expr()
            self.expect("op", ";")
            return ("assign", target, expr)
        if self.peek() == ("op", "("):
            args = self.parse_args()
            self.expect("op", ";")
            return ("call", target, args)
        raise SclError(f"cannot parse statement at {self.peek()}")

    def parse_if(self):
        key = (self.filename, self.line())
        self.expect("id", "IF")
        branches = []
        cond = self.parse_expr()
        self.expect("id", "THEN")
        body = self.parse_stmts(("ELSIF", "ELSE", "END_IF"))
        branches.append((cond, body))
        else_body = []
        while True:
            if self.accept("id", "ELSIF"):
                cond = self.parse_expr()
                self.expect("id", "THEN")
                branches.append((cond, self.parse_stmts(("ELSIF", "ELSE", "END_IF"))))
            elif self.accept("id", "ELSE"):
                else_body = self.parse_stmts(("END_IF",))
            else:
                break
        self.expect("id", "END_IF")
        self.accept("op", ";")
        for n in range(len(branches)):
            _register(key + (n,), f"{self.block} line {key[1]}: IF branch {n + 1}")
        _register(key + ("else",), f"{self.block} line {key[1]}: IF else/no branch")
        return ("if", branches, else_body, key)

    def parse_case(self):
        key = (self.filename, self.line())
        self.expect("id", "CASE")
        sel = self.parse_expr()
        self.expect("id", "OF")
        cases, else_body = [], []
        while True:
            if self.accept("id", "END_CASE"):
                break
            if self.accept("id", "ELSE"):
                else_body = self.parse_stmts(("END_CASE",))
                continue
            labels = [self.parse_expr()]
            while self.accept("op", ","):
                labels.append(self.parse_expr())
            self.expect("op", ":")
            body = []
            # a case body ends at the next "label:" or ELSE / END_CASE
            while not (self.is_id("ELSE", "END_CASE") or self._at_case_label()):
                s = self.parse_stmt()
                if s is not None:
                    body.append(s)
            cases.append((labels, body))
        self.accept("op", ";")
        for n in range(len(cases)):
            _register(key + (n,), f"{self.block} line {key[1]}: CASE label {n + 1}")
        _register(key + ("else",), f"{self.block} line {key[1]}: CASE else")
        return ("case", sel, cases, else_body, key)

    def _at_case_label(self):
        save = self.i
        try:
            tok = self.peek()
            if tok[0] not in ("lit", "lid", "qid", "id") or (tok[0] == "id" and tok[1] in ("IF", "CASE", "REGION")):
                return False
            self.parse_expr()
            while self.accept("op", ","):
                self.parse_expr()
            return self.peek() == ("op", ":")
        except SclError:
            return False
        finally:
            self.i = save

    def parse_args(self):
        self.expect("op", "(")
        args = []
        if not self.accept("op", ")"):
            pos = 0
            while True:
                if self.peek()[0] == "id" and self.peek(1) in (("op", ":="), ("op", "=>")):
                    name = self.next()[1].lower()
                    if self.accept("op", ":="):
                        args.append(("in", name, self.parse_expr()))
                    else:
                        self.expect("op", "=>")
                        args.append(("out", name, self.parse_designator()))
                else:
                    args.append(("in", f"_pos{pos}", self.parse_expr()))   # positional (builtins)
                    pos += 1
                if self.accept("op", ")"):
                    break
                self.expect("op", ",")
        return args

    # expressions (SCL precedence: unary/NOT > * / MOD > + - > comparison > = <> > AND > XOR > OR)
    def parse_expr(self):
        return self._binary(0)

    LEVELS = [("OR",), ("XOR",), ("AND", "&"), ("=", "<>"), ("<", ">", "<=", ">="), ("+", "-"),
              ("*", "/", "MOD")]

    def _binary(self, level):
        if level == len(self.LEVELS):
            return self._unary()
        left = self._binary(level + 1)
        while True:
            tok = self.peek()
            if tok[0] in ("op", "id") and tok[1] in self.LEVELS[level]:
                self.next()
                right = self._binary(level + 1)
                left = ("bin", tok[1], left, right)
            else:
                return left

    def _unary(self):
        if self.accept("id", "NOT"):
            return ("not", self._unary())
        if self.accept("op", "-"):
            return ("neg", self._unary())
        if self.accept("op", "+"):
            return self._unary()
        return self._primary()

    def _primary(self):
        tok = self.peek()
        if tok[0] == "lit":
            self.next()
            return ("lit", tok[1])
        if self.accept("op", "("):
            e = self.parse_expr()
            self.expect("op", ")")
            return e
        d = self.parse_designator()
        if self.peek() == ("op", "("):
            return ("fcall", d, self.parse_args())
        return d

    def parse_designator(self):
        tok = self.next()
        if tok[0] == "lid":
            node = ("local", tok[1])
        elif tok[0] == "qid":
            node = ("global", tok[1])
        elif tok[0] == "id":
            node = ("name", tok[1])
        else:
            raise SclError(f"expected identifier, got {tok}")
        while True:
            if self.peek() == ("op", ".") and self.peek(1)[0] == "id":
                self.next()
                node = ("member", node, self.next()[1].lower())
            elif self.accept("op", "["):
                idx = self.parse_expr()
                self.expect("op", "]")
                node = ("index", node, idx)
            else:
                return node


# --------------------------------------------------------------------------- runtime
class Frame:
    def __init__(self, vars_obj, constants):
        self.vars = vars_obj
        self.constants = constants


class Plc:
    def __init__(self, *paths):
        self.now = 0
        self.types, self.fcs, self.fbs, self.obs, self.dbs = {}, {}, {}, {}, {}
        pending_dbs = []
        for p in paths:
            with open(p, encoding="utf-8-sig") as f:
                for b in Parser(tokenize(f.read()), filename=p.replace("\\", "/").split("/")[-1]).parse_unit():
                    key = b.name.lower()
                    if b.kind == "TYPE":
                        self.types[key] = b
                    elif b.kind == "FUNCTION":
                        self.fcs[key] = b
                    elif b.kind == "FUNCTION_BLOCK":
                        self.fbs[key] = b
                    elif b.kind == "ORGANIZATION_BLOCK":
                        self.obs[key] = b
                    else:
                        pending_dbs.append(b)
        for b in pending_dbs:
            if b.instance_of:
                self.dbs[b.name.lower()] = self.new_instance(b.instance_of)
            else:
                obj = Obj(b.name)
                for name, typ, init in b.sections.get("static", []):
                    obj.define(name, self.make_value(typ, init))
                self.dbs[b.name.lower()] = obj

    # instances
    _SYSTEM_FBS = {"TON_TIME": Ton, "TON": Ton,
                   "R_TRIG": lambda: Trig(True), "F_TRIG": lambda: Trig(False)}

    def make_value(self, typ, init=None):
        kind, info = typ
        if kind == "prim":
            return self._make_prim(info, init)
        if kind == "struct":
            return self._make_struct("Struct", info)
        return self._make_named(info)

    def _make_prim(self, info, init):
        if info in self._SYSTEM_FBS:
            return self._SYSTEM_FBS[info]()
        if info not in _PRIM_DEFAULT:
            raise SclError(f"unsupported data type {info}")
        return self.const_eval(init) if init is not None else _PRIM_DEFAULT[info]

    def _make_struct(self, typename, members):
        obj = Obj(typename)
        for name, mtyp, minit in members:
            obj.define(name, self.make_value(mtyp, minit))
        return obj

    def _make_named(self, info):
        key = info.lower()
        if key in self.types:
            obj = Obj(info)
            for name, mtyp, minit in self.types[key].sections["static"]:
                obj.define(name, self.make_value(mtyp, minit))
            return obj
        if key in self.fbs:
            return self.new_instance(info)
        raise SclError(f"unknown type {info}")

    def new_instance(self, fbname):
        fb = self.fbs[fbname.lower()]
        inst = Obj(fb.name)
        for section in ("input", "output", "inout", "static"):
            for name, typ, init in fb.sections.get(section, []):
                inst.define(name, self.make_value(typ, init))
        object.__setattr__(inst, "_fb", fb)
        return inst

    def const_eval(self, expr):
        return self.eval(expr, Frame(Obj(), {}))

    def constants_of(self, block):
        return {name: self.const_eval(init) for name, _t, init in block.sections.get("constant", [])}

    # public API for tests
    def db(self, name):
        return self.dbs[name.lower()]

    def scan(self, dt_ms=10, ob="OB_CellSorting"):
        self.now += dt_ms
        blk = self.obs[ob.lower()]
        self.exec_body(blk.body, Frame(Obj(blk.name), self.constants_of(blk)))

    def call_fc(self, name, **kwargs):
        return self._call_fc(self.fcs[name.lower()], {k.lower(): v for k, v in kwargs.items()})

    def call_fb(self, inst, dt_ms=0, **kwargs):
        self.now += dt_ms
        for k, v in kwargs.items():
            setattr(inst, k, copy.deepcopy(v))
        self._exec_fb(inst)

    # execution
    def _exec_fb(self, inst):
        if isinstance(inst, (Ton, Trig)):
            inst.execute(self.now)
            return
        fb = object.__getattribute__(inst, "_fb")
        for name, typ, init in fb.sections.get("temp", []):
            inst.define(name, self.make_value(typ, init))
        self.exec_body(fb.body, Frame(inst, self.constants_of(fb)))

    def _call_fc(self, fc, args):
        vars_obj = Obj(fc.name)
        for section in ("input", "output", "inout", "temp", "static"):
            for name, typ, init in fc.sections.get(section, []):
                vars_obj.define(name, self.make_value(typ, init))
        for k, v in args.items():
            setattr(vars_obj, k, copy.deepcopy(v))
        vars_obj.define(fc.name.lower(), self.make_value(fc.ret_type))
        self.exec_body(fc.body, Frame(vars_obj, self.constants_of(fc)))
        return getattr(vars_obj, fc.name.lower())

    def exec_body(self, stmts, frame):
        for s in stmts:
            self.exec_stmt(s, frame)

    def exec_stmt(self, s, frame):
        handler = getattr(self, "_st_" + s[0], None)
        if handler is None:
            raise SclError(f"unknown statement {s[0]}")
        handler(s, frame)

    def _st_assign(self, s, frame):
        self.assign(s[1], self.eval(s[2], frame), frame)

    def _st_block(self, s, frame):
        self.exec_body(s[1], frame)

    def _st_if(self, s, frame):
        for n, (cond, body) in enumerate(s[1]):
            if self.eval(cond, frame):
                COVERAGE["hit"].add(s[3] + (n,))
                self.exec_body(body, frame)
                return
        COVERAGE["hit"].add(s[3] + ("else",))
        self.exec_body(s[2], frame)

    def _st_case(self, s, frame):
        sel = self.eval(s[1], frame)
        for n, (labels, body) in enumerate(s[2]):
            if any(self.eval(lab, frame) == sel for lab in labels):
                COVERAGE["hit"].add(s[4] + (n,))
                self.exec_body(body, frame)
                return
        COVERAGE["hit"].add(s[4] + ("else",))
        self.exec_body(s[3], frame)

    def _st_call(self, s, frame):
        inst = self.eval(s[1], frame)
        if not isinstance(inst, Obj):
            raise SclError(f"call target is not an FB instance: {s[1]}")
        outs = [(name, expr) for direction, name, expr in s[2] if direction == "out"]
        for direction, name, expr in s[2]:
            if direction == "in":
                setattr(inst, name, copy.deepcopy(self.eval(expr, frame)))
        self._exec_fb(inst)
        for name, target in outs:
            self.assign(target, copy.deepcopy(getattr(inst, name)), frame)

    def assign(self, target, value, frame):
        if isinstance(value, Obj):
            value = copy.deepcopy(value)
        kind = target[0]
        if kind == "local":
            if frame.vars.has(target[1]):
                setattr(frame.vars, target[1], value)
                return
            raise SclError(f"assignment to unknown local #{target[1]}")
        if kind == "member":
            setattr(self.eval(target[1], frame), target[2], value)
            return
        raise SclError(f"cannot assign to {target}")

    def eval(self, e, frame):
        handler = getattr(self, "_ev_" + e[0], None)
        if handler is None:
            raise SclError(f"cannot evaluate {e}")
        return handler(e, frame)

    def _ev_lit(self, e, frame):
        return e[1]

    def _ev_local(self, e, frame):
        name = e[1]
        if frame.vars.has(name):
            return getattr(frame.vars, name)
        if name in frame.constants:
            return frame.constants[name]
        raise SclError(f"unknown local #{name}")

    def _ev_global(self, e, frame):
        key = e[1].lower()
        if key not in self.dbs:
            raise SclError(f"unknown global \"{e[1]}\"")
        return self.dbs[key]

    def _ev_member(self, e, frame):
        return getattr(self.eval(e[1], frame), e[2])

    def _ev_not(self, e, frame):
        return not self.eval(e[1], frame)

    def _ev_neg(self, e, frame):
        return -self.eval(e[1], frame)

    def _ev_bin(self, e, frame):
        return self._binop(e[1], self.eval(e[2], frame), self.eval(e[3], frame))

    def _ev_fcall(self, e, frame):
        target, args = e[1], e[2]
        argvals = {name: self.eval(expr, frame) for _d, name, expr in args}
        if target[0] == "global" and target[1].lower() in self.fcs:
            return self._call_fc(self.fcs[target[1].lower()], argvals)
        if target[0] == "name":
            return self._builtin(target[1], list(argvals.values()), args, frame)
        raise SclError(f"unknown function {target}")

    def _ev_name(self, e, frame):
        raise SclError(f"bare identifier {e[1]} (missing # or quotes?)")

    def _builtin(self, name, values, args, frame):
        if re.fullmatch(r"(U?S?D?INT|BYTE|WORD|DWORD|TIME)_TO_(L?REAL)", name):
            return float(values[0])
        if re.fullmatch(r"(L?REAL)_TO_(U?S?D?INT)", name):
            return int(round(values[0]))
        if re.fullmatch(r"(U?S?D?INT|TIME)_TO_(U?S?D?INT|TIME)", name):
            return int(values[0])
        if name == "ABS":
            return abs(values[0])
        raise SclError(f"builtin {name} not supported")

    @staticmethod
    def _binop(op, a, b):
        fn = _BINOPS.get(op)
        if fn is None:
            raise SclError(f"operator {op} not supported")
        return fn(a, b)


def _logic(bool_fn, int_fn):
    return lambda a, b: bool_fn(a, b) if isinstance(a, bool) else int_fn(a, b)


def _divide(a, b):
    if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool):
        return int(a / b)            # SCL integer division truncates toward zero
    return a / b


_BINOPS = {
    "AND": _logic(lambda a, b: a and b, lambda a, b: a & b),
    "&": _logic(lambda a, b: a and b, lambda a, b: a & b),
    "OR": _logic(lambda a, b: a or b, lambda a, b: a | b),
    "XOR": _logic(lambda a, b: a != b, lambda a, b: a ^ b),
    "=": lambda a, b: a == b, "<>": lambda a, b: a != b,
    "<": lambda a, b: a < b, ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
    "+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
    "/": _divide, "MOD": lambda a, b: int(a - b * int(a / b)),
}
