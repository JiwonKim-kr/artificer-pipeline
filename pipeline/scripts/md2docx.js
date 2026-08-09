// 제출용 마크다운 → Word 변환기.
// 이 문서에서 실제로 쓰는 문법만 다룬다: # 헤딩, 표, 코드펜스, 불릿, 인용, 수평선,
// 인라인 **굵게** / `코드`. 범용 파서가 아니라 04_ai_tech_doc.md 전용.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, PageBreak, ImageRun,
} = require("docx");

const SRC = process.argv[2];
const OUT = process.argv[3];
const TITLE = process.argv[4] || "문서";

const BODY = "맑은 고딕";
const MONO = "D2Coding, Consolas";
const ACCENT = "1F3864";   // 제목 남색
const RULE = "BFBFBF";
const HEAD_BG = "E7E6E6";  // 표 헤더 음영
const CODE_BG = "F2F2F2";

const PAGE_W = 12240, MARGIN = 1080;          // Letter, 0.75인치 여백
const CONTENT_W = PAGE_W - MARGIN * 2;

/** PNG 헤더(IHDR)에서 픽셀 크기를 읽는다. 외부 이미지 라이브러리 불필요. */
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

/** 인라인 **굵게** · `코드` 를 TextRun 배열로. */
function runs(text, opts = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: BODY, ...opts }));
    const tok = m[0];
    if (tok.startsWith("**")) {
      out.push(new TextRun({ text: tok.slice(2, -2), bold: true, font: BODY, ...opts }));
    } else {
      out.push(new TextRun({ text: tok.slice(1, -1), font: MONO, size: 18, ...opts }));
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: BODY, ...opts }));
  return out.length ? out : [new TextRun({ text: "", font: BODY })];
}

function splitRow(line) {
  return line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

/** 마크다운 표 → docx Table. columnWidths + 셀 width 를 DXA 로 함께 지정(구글독스 호환). */
function makeTable(rows) {
  const header = splitRow(rows[0]);
  const bodyRows = rows.slice(2).map(splitRow);
  const n = header.length;
  const base = Math.floor(CONTENT_W / n);
  const widths = Array(n).fill(base);
  widths[n - 1] = CONTENT_W - base * (n - 1); // 합계 보정

  const cell = (txt, isHead, i) =>
    new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: isHead ? { type: ShadingType.CLEAR, fill: HEAD_BG, color: "auto" } : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: [new Paragraph({
        spacing: { before: 20, after: 20 },
        children: runs(txt, isHead ? { bold: true, size: 19 } : { size: 19 }),
      })],
    });

  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_W, type: WidthType.DXA },
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, true, i)) }),
      ...bodyRows.map((r) => new TableRow({
        children: Array.from({ length: n }, (_, i) => cell(r[i] ?? "", false, i)),
      })),
    ],
  });
}

function codeBlock(lines) {
  return lines.map((l, idx) => new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: CODE_BG, color: "auto" },
    spacing: { before: idx === 0 ? 100 : 0, after: idx === lines.length - 1 ? 100 : 0, line: 240 },
    indent: { left: 220 },
    children: [new TextRun({ text: l || " ", font: MONO, size: 17 })],
  }));
}

function convert(md) {
  const lines = md.split(/\r?\n/);
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // 코드 펜스
    if (/^```/.test(line)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(...codeBlock(buf));
      continue;
    }

    // 표
    if (/^\|/.test(line) && i + 1 < lines.length && /^\|[\s:|-]+\|?$/.test(lines[i + 1])) {
      const buf = [];
      while (i < lines.length && /^\|/.test(lines[i])) buf.push(lines[i++]);
      out.push(makeTable(buf));
      out.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
      continue;
    }

    // 이미지 ![캡션](경로) — 본문 폭에 맞춰 축소, 아래에 캡션
    const im = line.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/);
    if (im) {
      const abs = path.resolve(path.dirname(SRC), im[2]);
      if (fs.existsSync(abs)) {
        const dim = pngSize(abs);
        const maxW = CONTENT_W;                       // DXA
        const wEmu = Math.min(dim.w * 9525, maxW * 635); // px→EMU / DXA→EMU
        const scale = wEmu / (dim.w * 9525);
        out.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 140, after: 60 },
          children: [new ImageRun({
            type: "png",
            data: fs.readFileSync(abs),
            transformation: {
              width: Math.round(dim.w * scale * 0.75),   // EMU→pt(96dpi 기준 px)
              height: Math.round(dim.h * scale * 0.75),
            },
          })],
        }));
        if (im[1]) {
          out.push(new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { after: 180 },
            children: [new TextRun({ text: im[1], font: BODY, size: 16, color: "666666", italics: true })],
          }));
        }
      }
      i++;
      continue;
    }

    // 수평선
    if (/^---+$/.test(line.trim())) {
      out.push(new Paragraph({
        spacing: { before: 120, after: 160 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE, space: 1 } },
        children: [],
      }));
      i++;
      continue;
    }

    // 헤딩
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      const map = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3, 4: HeadingLevel.HEADING_4 };
      const size = { 1: 30, 2: 25, 3: 22, 4: 20 }[lvl];
      out.push(new Paragraph({
        heading: map[lvl],
        spacing: { before: lvl === 1 ? 320 : 240, after: 120 },
        children: runs(h[2], { bold: true, color: ACCENT, size }),
      }));
      i++;
      continue;
    }

    // 인용
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
      buf.forEach((b, idx) => out.push(new Paragraph({
        spacing: { before: idx === 0 ? 100 : 0, after: idx === buf.length - 1 ? 120 : 0 },
        indent: { left: 260 },
        border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 8 } },
        children: runs(b.replace(/^[-•]\s*/, b.startsWith("- ") ? "• " : ""), { italics: true, size: 19 }),
      })));
      continue;
    }

    // 불릿 / 번호
    const b = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (b) {
      const depth = Math.min(2, Math.floor(b[1].length / 2));
      const marker = /\d/.test(b[2]) ? `${b[2]} ` : "• ";
      out.push(new Paragraph({
        spacing: { after: 60 },
        indent: { left: 260 + depth * 260, hanging: 200 },
        children: runs(marker + b[3]),
      }));
      i++;
      continue;
    }

    // 빈 줄 / 본문
    if (line.trim() === "") {
      out.push(new Paragraph({ spacing: { after: 60 }, children: [] }));
    } else {
      out.push(new Paragraph({ spacing: { after: 100, line: 280 }, children: runs(line) }));
    }
    i++;
  }
  return out;
}

const md = fs.readFileSync(SRC, "utf8");
const doc = new Document({
  creator: "TeamNuN",
  title: TITLE,
  styles: { default: { document: { run: { font: BODY, size: 20 } } } },
  sections: [{
    properties: {
      page: { size: { width: PAGE_W, height: 15840 }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } },
    },
    children: convert(md),
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("작성 완료:", OUT, (buf.length / 1024).toFixed(0) + " KB");
});
