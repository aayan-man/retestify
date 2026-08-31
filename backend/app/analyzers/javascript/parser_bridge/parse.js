#!/usr/bin/env node
// CLI: parse.js <file>
// Reads one JS/TS/JSX/TSX file and prints a JSON IR on stdout:
//   { components: [...], test_cases: [...], imports: [...], parse_errors: [...] }
// Never throws on a syntax error — collects it into parse_errors instead, so
// the Python side's contract (never raise on a bad file) holds across the
// subprocess boundary too.

const fs = require("fs");
const crypto = require("crypto");
const parser = require("@babel/parser");
const traverse = require("@babel/traverse").default;

const filePath = process.argv[2];
if (!filePath) {
  console.error("usage: parse.js <file>");
  process.exit(1);
}

const source = fs.readFileSync(filePath, "utf-8");
const lines = source.split("\n");

function hashSegment(startLine, endLine) {
  const segment = lines.slice(startLine - 1, endLine).join("\n");
  return "sha256:" + crypto.createHash("sha256").update(segment, "utf-8").digest("hex");
}

function emit(payload) {
  process.stdout.write(JSON.stringify(payload));
}

let ast;
try {
  ast = parser.parse(source, {
    sourceType: "module",
    plugins: [
      "typescript",
      "jsx",
      "classProperties",
      "classPrivateProperties",
      "classPrivateMethods",
      "decorators-legacy",
      "objectRestSpread",
      "optionalChaining",
      "nullishCoalescingOperator",
    ],
    errorRecovery: true,
  });
} catch (e) {
  emit({ components: [], test_cases: [], imports: [], parse_errors: [String(e.message || e)] });
  process.exit(0);
}

const components = [];
const testCases = [];
const imports = [];

const DECISION_TYPES = new Set([
  "IfStatement", "ForStatement", "ForInStatement", "ForOfStatement",
  "WhileStatement", "DoWhileStatement", "CatchClause",
  "ConditionalExpression", "LogicalExpression", "SwitchCase",
]);
const NEST_TYPES = new Set([
  "IfStatement", "ForStatement", "ForInStatement", "ForOfStatement",
  "WhileStatement", "DoWhileStatement", "TryStatement", "SwitchStatement",
]);
const TEST_CALL_NAMES = new Set(["test", "it"]);

function complexityOf(path) {
  let count = 1;
  path.traverse({
    enter(inner) {
      if (DECISION_TYPES.has(inner.node.type)) count += 1;
    },
  });
  return count;
}

function nestingDepthOf(node) {
  let maxDepth = 0;
  function walk(n, depth) {
    if (!n || typeof n.type !== "string") return;
    maxDepth = Math.max(maxDepth, depth);
    for (const key in n) {
      if (key === "loc" || key === "start" || key === "end" || key === "range" || key === "leadingComments" || key === "trailingComments") continue;
      const value = n[key];
      if (Array.isArray(value)) {
        for (const v of value) walk(v, NEST_TYPES.has(n.type) ? depth + 1 : depth);
      } else if (value && typeof value.type === "string") {
        walk(value, NEST_TYPES.has(n.type) ? depth + 1 : depth);
      }
    }
  }
  walk(node, 0);
  return maxDepth;
}

function paramCount(node) {
  return (node.params || []).length;
}

function signatureOf(name, node) {
  const params = (node.params || []).map((p) => {
    if (p.type === "Identifier") return p.name;
    if (p.type === "AssignmentPattern" && p.left.type === "Identifier") return p.left.name;
    if (p.type === "RestElement" && p.argument && p.argument.type === "Identifier") return "..." + p.argument.name;
    if (p.type === "ObjectPattern") return "{...}";
    return "?";
  });
  const asyncPrefix = node.async ? "async " : "";
  return `${asyncPrefix}function ${name}(${params.join(", ")})`;
}

function addComponent({ kind, name, qualifiedName, parentQualifiedName, parentLine, path, node }) {
  const lineStart = node.loc.start.line;
  const lineEnd = node.loc.end.line;
  components.push({
    kind,
    name,
    qualified_name: qualifiedName,
    parent_qualified_name: parentQualifiedName || null,
    parent_line: parentLine || null,
    line_start: lineStart,
    line_end: lineEnd,
    signature: kind === "class" ? null : signatureOf(name, node),
    docstring: null,
    calls: [],
    metrics: {
      loc: lineEnd - lineStart + 1,
      cyclomatic_complexity: kind === "class" ? 1 : complexityOf(path),
      nesting_depth: kind === "class" ? 0 : nestingDepthOf(node),
      num_params: kind === "class" ? 0 : paramCount(node),
    },
    content_hash: hashSegment(lineStart, lineEnd),
  });
}

function stringArg(node) {
  const arg = (node.arguments || [])[0];
  if (arg && arg.type === "StringLiteral") return arg.value;
  return "anonymous";
}

function slugify(text) {
  return text.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "anonymous";
}

traverse(ast, {
  ImportDeclaration(path) {
    imports.push({ to_module: path.node.source.value });
  },
  CallExpression(path) {
    const callee = path.node.callee;
    const calleeName = callee.type === "Identifier" ? callee.name
      : (callee.type === "MemberExpression" && callee.object.type === "Identifier") ? callee.object.name
      : null;
    if (calleeName && TEST_CALL_NAMES.has(calleeName)) {
      const line = path.node.loc.start.line;
      const endLine = path.node.loc.end.line;
      testCases.push({
        name: `test_${slugify(stringArg(path.node))}`,
        line_start: line,
        line_end: endLine,
        content_hash: hashSegment(line, endLine),
      });
    }
  },
  FunctionDeclaration(path) {
    if (!path.node.id) return;
    if (path.parentPath.isExportDefaultDeclaration() || path.parentPath.isProgram() || path.parentPath.isExportNamedDeclaration()) {
      const name = path.node.id.name;
      addComponent({ kind: "function", name, qualifiedName: name, path, node: path.node });
    }
  },
  VariableDeclarator(path) {
    const init = path.node.init;
    if (!init) return;
    if (init.type !== "ArrowFunctionExpression" && init.type !== "FunctionExpression") return;
    if (path.node.id.type !== "Identifier") return;
    if (!path.parentPath.parentPath.isProgram() && !path.parentPath.parentPath.isExportNamedDeclaration()) return;
    const name = path.node.id.name;
    addComponent({ kind: "function", name, qualifiedName: name, path: path.get("init"), node: init });
  },
  ClassDeclaration(path) {
    if (!path.node.id) return;
    if (!path.parentPath.isProgram() && !path.parentPath.isExportNamedDeclaration() && !path.parentPath.isExportDefaultDeclaration()) return;
    const className = path.node.id.name;
    const classLine = path.node.loc.start.line;
    addComponent({ kind: "class", name: className, qualifiedName: className, path, node: path.node });

    const bodyPaths = path.get("body.body");
    for (const memberPath of bodyPaths) {
      const member = memberPath.node;
      if (member.type !== "ClassMethod" && member.type !== "ClassPrivateMethod") continue;
      const methodName = member.key.name || member.key.value || "anonymous";
      addComponent({
        kind: "method",
        name: methodName,
        qualifiedName: `${className}.${methodName}`,
        parentQualifiedName: className,
        parentLine: classLine,
        path: memberPath,
        node: member,
      });
    }
  },
});

emit({ components, test_cases: testCases, imports, parse_errors: [] });
