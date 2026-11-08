var EasyConvertEquation = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

  // static/scripts/hwp-equation.vendor.ts
  var hwp_equation_vendor_exports = {};
  __export(hwp_equation_vendor_exports, {
    HWP_EQ_GREEK: () => HWP_EQ_GREEK,
    HWP_EQ_SYMBOLS: () => HWP_EQ_SYMBOLS,
    hwpEquationToLaTeX: () => hwpEquationToLaTeX,
    hwpEquationToMathML: () => hwpEquationToMathML
  });
  var CorruptStreamError = class extends Error {
  };
  var HWP_EQ_GREEK = {
    alpha: { mathml: "\u03B1", latex: "\\alpha" },
    beta: { mathml: "\u03B2", latex: "\\beta" },
    gamma: { mathml: "\u03B3", latex: "\\gamma" },
    delta: { mathml: "\u03B4", latex: "\\delta" },
    epsilon: { mathml: "\u03B5", latex: "\\epsilon" },
    zeta: { mathml: "\u03B6", latex: "\\zeta" },
    eta: { mathml: "\u03B7", latex: "\\eta" },
    theta: { mathml: "\u03B8", latex: "\\theta" },
    iota: { mathml: "\u03B9", latex: "\\iota" },
    kappa: { mathml: "\u03BA", latex: "\\kappa" },
    lambda: { mathml: "\u03BB", latex: "\\lambda" },
    mu: { mathml: "\u03BC", latex: "\\mu" },
    nu: { mathml: "\u03BD", latex: "\\nu" },
    xi: { mathml: "\u03BE", latex: "\\xi" },
    pi: { mathml: "\u03C0", latex: "\\pi" },
    rho: { mathml: "\u03C1", latex: "\\rho" },
    sigma: { mathml: "\u03C3", latex: "\\sigma" },
    tau: { mathml: "\u03C4", latex: "\\tau" },
    upsilon: { mathml: "\u03C5", latex: "\\upsilon" },
    phi: { mathml: "\u03C6", latex: "\\phi" },
    chi: { mathml: "\u03C7", latex: "\\chi" },
    psi: { mathml: "\u03C8", latex: "\\psi" },
    omega: { mathml: "\u03C9", latex: "\\omega" },
    Gamma: { mathml: "\u0393", latex: "\\Gamma" },
    Delta: { mathml: "\u0394", latex: "\\Delta" },
    Theta: { mathml: "\u0398", latex: "\\Theta" },
    Lambda: { mathml: "\u039B", latex: "\\Lambda" },
    Xi: { mathml: "\u039E", latex: "\\Xi" },
    Pi: { mathml: "\u03A0", latex: "\\Pi" },
    Sigma: { mathml: "\u03A3", latex: "\\Sigma" },
    Phi: { mathml: "\u03A6", latex: "\\Phi" },
    Psi: { mathml: "\u03A8", latex: "\\Psi" },
    Omega: { mathml: "\u03A9", latex: "\\Omega" }
  };
  var HWP_EQ_SYMBOLS = {
    pm: { mathml: "\xB1", latex: "\\pm" },
    mp: { mathml: "\u2213", latex: "\\mp" },
    times: { mathml: "\xD7", latex: "\\times" },
    div: { mathml: "\xF7", latex: "\\div" },
    cdot: { mathml: "\xB7", latex: "\\cdot" },
    circ: { mathml: "\u2218", latex: "\\circ" },
    le: { mathml: "\u2264", latex: "\\le" },
    ge: { mathml: "\u2265", latex: "\\ge" },
    ne: { mathml: "\u2260", latex: "\\ne" },
    approx: { mathml: "\u2248", latex: "\\approx" },
    equiv: { mathml: "\u2261", latex: "\\equiv" },
    sim: { mathml: "\u223C", latex: "\\sim" },
    propto: { mathml: "\u221D", latex: "\\propto" },
    to: { mathml: "\u2192", latex: "\\to" },
    rightarrow: { mathml: "\u2192", latex: "\\to" },
    leftarrow: { mathml: "\u2190", latex: "\\leftarrow" },
    infty: { mathml: "\u221E", latex: "\\infty" },
    inf: { mathml: "\u221E", latex: "\\infty" },
    partial: { mathml: "\u2202", latex: "\\partial" },
    nabla: { mathml: "\u2207", latex: "\\nabla" },
    forall: { mathml: "\u2200", latex: "\\forall" },
    exists: { mathml: "\u2203", latex: "\\exists" },
    in: { mathml: "\u2208", latex: "\\in" },
    notin: { mathml: "\u2209", latex: "\\notin" },
    subset: { mathml: "\u2282", latex: "\\subset" },
    supset: { mathml: "\u2283", latex: "\\supset" },
    cup: { mathml: "\u222A", latex: "\\cup" },
    cap: { mathml: "\u2229", latex: "\\cap" },
    emptyset: { mathml: "\u2205", latex: "\\emptyset" },
    therefore: { mathml: "\u2234", latex: "\\therefore" },
    angle: { mathml: "\u2220", latex: "\\angle" },
    perp: { mathml: "\u22A5", latex: "\\perp" },
    prime: { mathml: "\u2032", latex: "\\prime" },
    cdots: { mathml: "\u22EF", latex: "\\cdots" },
    ldots: { mathml: "\u2026", latex: "\\ldots" },
    hbar: { mathml: "\u210F", latex: "\\hbar" }
  };
  var FUNCTION_NAMES = /* @__PURE__ */ new Set([
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "arcsin",
    "arccos",
    "arctan",
    "log",
    "ln",
    "exp",
    "det",
    "min",
    "max",
    "gcd",
    "mod"
  ]);
  var BIG_OPERATORS = {
    sum: { glyph: "\u2211", latex: "\\sum", stacked: true },
    prod: { glyph: "\u220F", latex: "\\prod", stacked: true },
    int: { glyph: "\u222B", latex: "\\int", stacked: false },
    oint: { glyph: "\u222E", latex: "\\oint", stacked: false },
    lim: { glyph: "lim", latex: "\\lim", stacked: true }
  };
  var ACCENTS = {
    hat: { glyph: "^", latex: "\\hat", under: false },
    bar: { glyph: "\xAF", latex: "\\bar", under: false },
    vec: { glyph: "\u2192", latex: "\\vec", under: false },
    dot: { glyph: "\u02D9", latex: "\\dot", under: false },
    ddot: { glyph: "\xA8", latex: "\\ddot", under: false },
    tilde: { glyph: "~", latex: "\\tilde", under: false },
    acute: { glyph: "\xB4", latex: "\\acute", under: false },
    grave: { glyph: "`", latex: "\\grave", under: false },
    check: { glyph: "\u02C7", latex: "\\check", under: false },
    under: { glyph: "_", latex: "\\underline", under: true }
  };
  var STYLES = {
    rm: { variant: "normal", latex: "\\mathrm" },
    it: { variant: "italic", latex: "\\mathit" },
    bold: { variant: "bold", latex: "\\mathbf" }
  };
  var MATRICES = {
    matrix: { open: "", close: "", env: "matrix" },
    pmatrix: { open: "(", close: ")", env: "pmatrix" },
    bmatrix: { open: "[", close: "]", env: "bmatrix" },
    dmatrix: { open: "|", close: "|", env: "vmatrix" }
  };
  var MULTI_CHARACTER_OPERATORS = {
    "<=": "\u2264",
    ">=": "\u2265",
    "!=": "\u2260",
    "->": "\u2192",
    "<-": "\u2190",
    "+-": "\xB1",
    "-+": "\u2213"
  };
  var MULTI_CHARACTER_LATEX = {
    "<=": "\\le ",
    ">=": "\\ge ",
    "!=": "\\ne ",
    "->": "\\to ",
    "<-": "\\leftarrow ",
    "+-": "\\pm ",
    "-+": "\\mp "
  };
  var has = (table, key) => Object.prototype.hasOwnProperty.call(table, key);
  var EM_SPACE = "1em";
  var THIN_SPACE = "0.17em";
  var MAX_SCRIPT_LENGTH = 1e5;
  var MAX_NESTING_DEPTH = 64;
  function invalid(script, detail) {
    const shown = script.length > 60 ? `${script.slice(0, 57)}...` : script;
    return new CorruptStreamError(`Invalid HWP equation "${shown}": ${detail}`);
  }
  var SINGLE_CHARACTER_TOKENS = {
    "{": "open",
    "}": "close",
    "^": "sup",
    _: "sub",
    "~": "tilde",
    "`": "tick",
    "&": "amp",
    "#": "hash"
  };
  function isKeyword(word) {
    return has(HWP_EQ_GREEK, word) || has(HWP_EQ_SYMBOLS, word) || FUNCTION_NAMES.has(word) || has(BIG_OPERATORS, word) || has(ACCENTS, word) || has(STYLES, word) || has(MATRICES, word) || ["over", "atop", "sqrt", "root", "of", "left", "right", "cases", "pile", "sub", "sup"].includes(word);
  }
  function keywordOf(word) {
    if (isKeyword(word)) return word;
    const lower = word.toLowerCase();
    if (!has(HWP_EQ_GREEK, word) && isKeyword(lower)) return lower;
    return null;
  }
  function tokenize(script) {
    const tokens = [];
    let spaced = false;
    let at = 0;
    while (at < script.length) {
      const char = script[at];
      if (/\s/.test(char)) {
        spaced = true;
        at += 1;
        continue;
      }
      const push = (token, length) => {
        tokens.push(token);
        at += length;
        spaced = false;
      };
      const kind = SINGLE_CHARACTER_TOKENS[char];
      if (kind) {
        push({ kind, text: char, spaced }, 1);
      } else if (char === '"') {
        const end = script.indexOf('"', at + 1);
        if (end < 0) throw invalid(script, "a quoted text is not closed");
        push({ kind: "text", text: script.slice(at + 1, end), spaced }, end + 1 - at);
      } else if (/[0-9]/.test(char)) {
        const match = /^\d+(?:\.\d+)?/.exec(script.slice(at));
        push({ kind: "number", text: match[0], spaced }, match[0].length);
      } else if (/[A-Za-z]/.test(char)) {
        const word = /^[A-Za-z]+/.exec(script.slice(at))[0];
        const keyword = keywordOf(word);
        if (keyword) {
          push({ kind: "word", text: keyword, spaced }, word.length);
        } else {
          [...word].forEach((letter, index) => tokens.push({ kind: "letter", text: letter, spaced: index === 0 ? spaced : false }));
          at += word.length;
          spaced = false;
        }
      } else {
        const pair = script.slice(at, at + 2);
        if (has(MULTI_CHARACTER_OPERATORS, pair)) push({ kind: "op", text: pair, spaced }, 2);
        else if (/\p{L}/u.test(char)) push({ kind: "letter", text: char, spaced }, char.length);
        else push({ kind: "op", text: char, spaced }, char.length);
      }
    }
    return tokens;
  }
  var EquationParser = class {
    constructor(script, tokens) {
      this.script = script;
      this.tokens = tokens;
      __publicField(this, "position", 0);
      __publicField(this, "depth", 0);
    }
    parse() {
      const nodes = this.parseSequence(() => false);
      if (this.position < this.tokens.length) throw invalid(this.script, `unexpected '${this.tokens[this.position].text}'`);
      return nodes;
    }
    peek() {
      return this.tokens[this.position];
    }
    enter() {
      this.depth += 1;
      if (this.depth > MAX_NESTING_DEPTH) throw invalid(this.script, `nesting deeper than ${MAX_NESTING_DEPTH} levels`);
    }
    leave() {
      this.depth -= 1;
    }
    /** Terms until `stop` matches the next token (not consumed) or the tokens end. */
    parseSequence(stop) {
      const nodes = [];
      for (let token = this.peek(); token && !stop(token); token = this.peek()) {
        if (token.kind === "close") throw invalid(this.script, "unexpected '}'");
        if (token.kind === "amp" || token.kind === "hash") throw invalid(this.script, `'${token.text}' is only valid inside a matrix`);
        if (token.kind === "word" && (token.text === "over" || token.text === "atop")) {
          this.position += 1;
          const numerator = nodes.pop();
          if (!numerator) throw invalid(this.script, `'${token.text}' has no numerator`);
          const denominator = this.parseTerm(`'${token.text}' has no denominator`);
          nodes.push({ type: "frac", num: numerator, den: denominator, atop: token.text === "atop", spaced: numerator.spaced });
          continue;
        }
        nodes.push(this.parseTerm("missing operand"));
      }
      return nodes;
    }
    /** An atom followed by its scripts. */
    parseTerm(missing) {
      let node = this.parseAtom(missing);
      for (; ; ) {
        const token = this.peek();
        const isSub = token && (token.kind === "sub" || token.kind === "word" && token.text === "sub");
        const isSup = token && (token.kind === "sup" || token.kind === "word" && token.text === "sup");
        if (!isSub && !isSup) return node;
        this.position += 1;
        const operand = this.parseAtom(`'${token.text}' has no script`);
        if (node.type === "script" && (isSub && !node.sub || isSup && !node.sup)) {
          if (isSub) node.sub = operand;
          else node.sup = operand;
        } else {
          node = { type: "script", base: node, sub: isSub ? operand : void 0, sup: isSup ? operand : void 0, stacked: false, spaced: node.spaced };
        }
      }
    }
    parseAtom(missing) {
      var _a;
      const token = this.peek();
      if (!token) throw invalid(this.script, missing);
      this.position += 1;
      const spaced = token.spaced;
      switch (token.kind) {
        case "number":
          return { type: "mn", text: token.text, spaced };
        case "letter":
          return { type: "mi", text: token.text, upright: false, spaced };
        case "text":
          return { type: "text", text: token.text, spaced };
        case "tilde":
          return { type: "space", width: EM_SPACE, latex: "\\quad ", spaced };
        case "tick":
          return { type: "space", width: THIN_SPACE, latex: "\\, ", spaced };
        case "op": {
          const mapped = MULTI_CHARACTER_OPERATORS[token.text];
          return { type: "mo", text: mapped != null ? mapped : token.text, latex: (_a = MULTI_CHARACTER_LATEX[token.text]) != null ? _a : latexOperator(token.text), spaced };
        }
        case "open":
          return this.parseGroup(spaced);
        case "close":
          throw invalid(this.script, "unexpected '}'");
        case "word":
          return this.parseKeyword(token.text, spaced, missing);
        default:
          throw invalid(this.script, `unexpected '${token.text}'`);
      }
    }
    parseGroup(spaced) {
      this.enter();
      const children = this.parseSequence((token) => token.kind === "close");
      if (!this.peek()) throw invalid(this.script, "a '{' is not closed");
      this.position += 1;
      this.leave();
      return { type: "row", children, braces: true, spaced };
    }
    parseKeyword(word, spaced, missing) {
      if (has(HWP_EQ_GREEK, word)) return { type: "mi", text: HWP_EQ_GREEK[word].mathml, upright: false, latex: HWP_EQ_GREEK[word].latex, spaced };
      if (has(HWP_EQ_SYMBOLS, word)) return { type: "mo", text: HWP_EQ_SYMBOLS[word].mathml, latex: HWP_EQ_SYMBOLS[word].latex, spaced };
      if (FUNCTION_NAMES.has(word)) return { type: "mi", text: word, upright: true, latex: `\\${word}`, spaced };
      if (has(BIG_OPERATORS, word)) return this.parseBigOperator(word, spaced);
      if (has(ACCENTS, word)) {
        const accent = ACCENTS[word];
        return { type: "accent", base: this.parseAtom(`'${word}' has no operand`), glyph: accent.glyph, latex: accent.latex, under: accent.under, spaced };
      }
      if (has(STYLES, word)) {
        return { type: "style", body: this.parseAtom(`'${word}' has no operand`), variant: STYLES[word].variant, latex: STYLES[word].latex, spaced };
      }
      if (word === "sqrt") return { type: "sqrt", body: this.parseTerm("'sqrt' has no operand"), spaced };
      if (word === "root") {
        const index = this.parseAtom("'root' has no index");
        const of = this.peek();
        if (!of || of.kind !== "word" || of.text !== "of") throw invalid(this.script, "'root' needs 'of' after its index");
        this.position += 1;
        return { type: "root", index, body: this.parseTerm("'of' has no operand"), spaced };
      }
      if (word === "left") return this.parseFence(spaced);
      if (has(MATRICES, word)) return this.parseTable(word, spaced);
      if (word === "cases" || word === "pile") return this.parseTable(word, spaced);
      throw invalid(this.script, `'${word}' cannot start a term (${missing})`);
    }
    parseBigOperator(word, spaced) {
      const operator = BIG_OPERATORS[word];
      const base = { type: "mo", text: operator.glyph, latex: operator.latex, spaced };
      let sub;
      let sup;
      for (let token = this.peek(); token; token = this.peek()) {
        const isSub = token.kind === "sub" || token.kind === "word" && token.text === "sub";
        const isSup = token.kind === "sup" || token.kind === "word" && token.text === "sup";
        if (!(isSub && !sub) && !(isSup && !sup)) break;
        this.position += 1;
        const operand = this.parseAtom(`'${word}' has no limit`);
        if (isSub) sub = operand;
        else sup = operand;
      }
      if (!sub && !sup) return base;
      return { type: "script", base, sub, sup, stacked: operator.stacked, spaced };
    }
    delimiter(after) {
      const token = this.peek();
      if (!token) throw invalid(this.script, `'${after}' has no delimiter`);
      this.position += 1;
      if (token.kind === "op" || token.kind === "letter" || token.kind === "open" || token.kind === "close") {
        return token.text === "." ? "" : token.text;
      }
      throw invalid(this.script, `'${token.text}' is not a delimiter`);
    }
    parseFence(spaced) {
      this.enter();
      const open = this.delimiter("left");
      const body = this.parseSequence((token) => token.kind === "word" && token.text === "right");
      if (!this.peek()) throw invalid(this.script, "'left' has no matching 'right'");
      this.position += 1;
      const close = this.delimiter("right");
      this.leave();
      return { type: "fence", open, close, body: { type: "row", children: body, braces: false, spaced: false }, spaced };
    }
    parseTable(word, spaced) {
      var _a;
      const opening = this.peek();
      if (!opening || opening.kind !== "open") throw invalid(this.script, `'${word}' needs a { } body`);
      this.position += 1;
      this.enter();
      const rows = [[]];
      for (; ; ) {
        const cell = this.parseSequence((token) => token.kind === "close" || token.kind === "amp" || token.kind === "hash");
        rows[rows.length - 1].push({ type: "row", children: cell, braces: false, spaced: false });
        const separator = this.peek();
        if (!separator) throw invalid(this.script, `the { } body of '${word}' is not closed`);
        this.position += 1;
        if (separator.kind === "close") break;
        if (separator.kind === "hash") rows.push([]);
      }
      this.leave();
      const style = (_a = MATRICES[word]) != null ? _a : word === "cases" ? { open: "{", close: "", env: "cases" } : { open: "", close: "", env: "matrix" };
      return { type: "table", rows, open: style.open, close: style.close, env: style.env, spaced };
    }
  };
  function latexOperator(text) {
    switch (text) {
      case "%":
        return "\\%";
      case "$":
        return "\\$";
      case "\\":
        return "\\backslash ";
      case "<":
        return "<";
      default:
        return text;
    }
  }
  function escapeXml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function mathmlOf(node) {
    switch (node.type) {
      case "mi":
        return node.upright ? `<mi mathvariant="normal">${escapeXml(node.text)}</mi>` : `<mi>${escapeXml(node.text)}</mi>`;
      case "mn":
        return `<mn>${node.text}</mn>`;
      case "mo":
        return `<mo>${escapeXml(node.text)}</mo>`;
      case "text":
        return `<mtext>${escapeXml(node.text)}</mtext>`;
      case "space":
        return `<mspace width="${node.width}"/>`;
      case "row":
        return node.children.length === 1 ? mathmlOf(node.children[0]) : `<mrow>${node.children.map(mathmlOf).join("")}</mrow>`;
      case "frac":
        return `<mfrac${node.atop ? ' linethickness="0"' : ""}>${mathmlOf(node.num)}${mathmlOf(node.den)}</mfrac>`;
      case "sqrt":
        return `<msqrt>${mathmlOf(node.body)}</msqrt>`;
      case "root":
        return `<mroot>${mathmlOf(node.body)}${mathmlOf(node.index)}</mroot>`;
      case "script":
        return scriptMathml(node);
      case "fence":
        return `<mrow><mo fence="true">${escapeXml(node.open)}</mo>${mathmlOf(node.body)}<mo fence="true">${escapeXml(node.close)}</mo></mrow>`;
      case "table":
        return tableMathml(node);
      case "accent":
        return node.under ? `<munder>${mathmlOf(node.base)}<mo>${escapeXml(node.glyph)}</mo></munder>` : `<mover accent="true">${mathmlOf(node.base)}<mo>${escapeXml(node.glyph)}</mo></mover>`;
      case "style":
        return `<mstyle mathvariant="${node.variant}">${mathmlOf(node.body)}</mstyle>`;
    }
  }
  function scriptMathml(node) {
    const base = mathmlOf(node.base);
    const [under, over, plain] = node.stacked ? ["munder", "mover", "munderover"] : ["msub", "msup", "msubsup"];
    if (node.sub && node.sup) return `<${plain}>${base}${mathmlOf(node.sub)}${mathmlOf(node.sup)}</${plain}>`;
    if (node.sub) return `<${under}>${base}${mathmlOf(node.sub)}</${under}>`;
    return `<${over}>${base}${mathmlOf(node.sup)}</${over}>`;
  }
  function tableMathml(node) {
    const align = node.env === "cases" ? ' columnalign="left"' : "";
    const rows = node.rows.map((row) => `<mtr>${row.map((cell) => `<mtd>${mathmlOf(cell)}</mtd>`).join("")}</mtr>`).join("");
    const table = `<mtable${align}>${rows}</mtable>`;
    if (!node.open && !node.close) return table;
    return `<mrow><mo fence="true">${escapeXml(node.open)}</mo>${table}<mo fence="true">${escapeXml(node.close)}</mo></mrow>`;
  }
  function latexSequence(nodes) {
    let out = "";
    nodes.forEach((node, index) => {
      const piece = latexOf(node);
      const needsSeparator = index > 0 && (node.spaced || /[A-Za-z]$/.test(out) && /^\\?[A-Za-z]/.test(piece) && /\\[A-Za-z]+$/.test(out));
      out += (needsSeparator && !out.endsWith(" ") ? " " : "") + piece;
    });
    return out;
  }
  function latexContent(node) {
    return node.type === "row" ? latexSequence(node.children) : latexOf(node);
  }
  function latexScriptOperand(node) {
    const content = latexContent(node);
    return node.type !== "row" && [...content.replace(/^\\/, "")].length === 1 ? content : `{${content}}`;
  }
  function latexOf(node) {
    var _a;
    switch (node.type) {
      case "mi":
        return (_a = node.latex) != null ? _a : node.text;
      case "mn":
        return node.text;
      case "mo":
        return node.latex;
      case "text":
        return `\\text{${node.text.replace(/[\\{}$&#%_^~]/g, (c) => `\\${c}`)}}`;
      case "space":
        return node.latex;
      case "row":
        return node.braces ? `{${latexSequence(node.children)}}` : latexSequence(node.children);
      case "frac":
        return fractionLatex(node);
      case "sqrt":
        return `\\sqrt{${latexContent(node.body)}}`;
      case "root":
        return `\\sqrt[${latexContent(node.index)}]{${latexContent(node.body)}}`;
      case "script":
        return `${latexOf(node.base)}${node.sub ? `_${latexScriptOperand(node.sub)}` : ""}${node.sup ? `^${latexScriptOperand(node.sup)}` : ""}`;
      case "fence":
        return `\\left${latexDelimiter(node.open)} ${latexContent(node.body)} \\right${latexDelimiter(node.close)}`;
      case "table": {
        const body = node.rows.map((row) => row.map(latexContent).join(" & ")).join(" \\\\ ");
        return `\\begin{${node.env}} ${body} \\end{${node.env}}`;
      }
      case "accent":
        return `${node.latex}{${latexContent(node.base)}}`;
      case "style":
        return `${node.latex}{${latexContent(node.body)}}`;
    }
  }
  function fractionLatex(node) {
    if (node.atop) return `{${latexContent(node.num)} \\atop ${latexContent(node.den)}}`;
    return `\\frac{${latexContent(node.num)}}{${latexContent(node.den)}}`;
  }
  function latexDelimiter(delimiter) {
    if (delimiter === "") return ".";
    if (delimiter === "{" || delimiter === "}") return `\\${delimiter}`;
    if (delimiter === "|") return "|";
    return delimiter;
  }
  function parseEquation(script) {
    if (script.length > MAX_SCRIPT_LENGTH) throw invalid(script, `longer than ${MAX_SCRIPT_LENGTH} characters`);
    return new EquationParser(script, tokenize(script)).parse();
  }
  function hwpEquationToMathML(script) {
    const nodes = parseEquation(script.trim());
    return `<math>${nodes.map(mathmlOf).join("")}</math>`;
  }
  function hwpEquationToLaTeX(script) {
    return latexSequence(parseEquation(script.trim()));
  }
  return __toCommonJS(hwp_equation_vendor_exports);
})();
