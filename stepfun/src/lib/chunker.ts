export interface DocumentChunk {
  text: string;
  index: number;
  heading: string;
  charCount: number;
}

export interface ChunkOptions {
  targetChars?: number;
  overlapChars?: number;
  maxChars?: number;
}

const DEFAULT_OPTIONS: Required<ChunkOptions> = {
  targetChars: 360,
  overlapChars: 60,
  maxChars: 420,
};

export function normalizeText(input: string): string {
  return String(input)
    .replace(/\r\n?/g, "\n")
    .replace(/\u0000/g, "")
    .replace(/\u200b/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function splitSentences(paragraph: string, maxChars: number): string[] {
  if (paragraph.length <= maxChars) return [paragraph];
  const pieces: string[] = [];
  let buffer = "";
  const sentences = paragraph.split(/(?<=[。！？!?；;])/u).filter(Boolean);
  for (const sentence of sentences) {
    if ((buffer + sentence).length <= maxChars) {
      buffer += sentence;
      continue;
    }
    if (buffer) {
      pieces.push(buffer.trim());
      buffer = "";
    }
    if (sentence.length <= maxChars) {
      buffer = sentence;
    } else {
      // Hard split a single very long sentence. Use code points so we do not
      // cut surrogate pairs in the middle.
      const chars = Array.from(sentence);
      for (let i = 0; i < chars.length; i += maxChars) {
        pieces.push(chars.slice(i, i + maxChars).join("").trim());
      }
    }
  }
  if (buffer.trim()) pieces.push(buffer.trim());
  return pieces.filter(Boolean);
}

/**
 * Heading-aware, paragraph-aware chunker. Chunks target ~360 Chinese characters
 * (well below the model's 512-token limit) and keep a 60-character overlap when
 * a paragraph has to be split.
 */
export function chunkDocument(
  input: string,
  options: ChunkOptions = {},
): DocumentChunk[] {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const text = normalizeText(input);
  if (!text) return [];

  const lines = text.split("\n");
  const sections: { heading: string; paragraphs: string[] }[] = [];
  let current = { heading: "", paragraphs: [] as string[] };
  let paragraph: string[] = [];

  const flushParagraph = () => {
    const value = paragraph.join("\n").trim();
    if (value) current.paragraphs.push(value);
    paragraph = [];
  };
  const flushSection = () => {
    flushParagraph();
    if (current.heading || current.paragraphs.length) sections.push(current);
    current = { heading: "", paragraphs: [] };
  };

  for (const line of lines) {
    const headingMatch = line.match(/^#{1,6}\s+(.+?)\s*$/);
    if (headingMatch) {
      flushSection();
      current.heading = headingMatch[1].trim();
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      continue;
    }
    paragraph.push(line);
  }
  flushSection();

  if (sections.length === 0) sections.push({ heading: "", paragraphs: [text] });

  const chunks: DocumentChunk[] = [];
  for (const section of sections) {
    let buffer = "";
    const push = (value: string) => {
      const clean = value.trim();
      if (!clean) return;
      chunks.push({
        text: clean,
        index: chunks.length,
        heading: section.heading,
        charCount: clean.length,
      });
    };

    for (const rawParagraph of section.paragraphs) {
      const pieces = splitSentences(rawParagraph, opts.maxChars);
      for (const piece of pieces) {
        if (!buffer) {
          buffer = piece;
          continue;
        }
        if (buffer.length + 2 + piece.length <= opts.targetChars) {
          buffer += `\n\n${piece}`;
          continue;
        }
        push(buffer);
        const overlap = takeTail(buffer, opts.overlapChars);
        buffer = overlap ? `${overlap}\n${piece}` : piece;
        if (buffer.length > opts.maxChars) {
          push(buffer.slice(0, opts.maxChars));
          buffer = buffer.slice(opts.maxChars - opts.overlapChars);
        }
      }
    }
    if (buffer) push(buffer);
  }
  return chunks.map((chunk, index) => ({ ...chunk, index }));
}

function takeTail(text: string, size: number): string {
  if (size <= 0) return "";
  const chars = Array.from(text);
  return chars.slice(Math.max(0, chars.length - size)).join("").trim();
}

export function countWords(text: string): number {
  const cjk = (text.match(/[\p{Script=Han}]/gu) || []).length;
  const latin = (text.match(/[A-Za-z0-9_]+/g) || []).length;
  return cjk + latin;
}
