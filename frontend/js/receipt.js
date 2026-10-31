// Receipt scan. The text recognition (Tesseract.js) runs on the phone, so the
// photo never leaves the device; only the recognized text goes to the server,
// which finds store, date, total and items (billbuddy.ml.receipt_ocr).

// Loaded only when someone scans for the first time (about 3 MB incl. German language data)
const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js";
let tesseractLoading;

export function loadTesseract() {
  tesseractLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = TESSERACT_URL;
    script.onload = () => resolve(window.Tesseract);
    script.onerror = () => {
      tesseractLoading = null;
      reject(new Error("Die Texterkennung konnte nicht geladen werden. Bist du online?"));
    };
    document.head.append(script);
  });
  return tesseractLoading;
}

// The photo as a bitmap, turned the right way round
export function loadPhoto(file) {
  return createImageBitmap(file, { imageOrientation: "from-image" });
}

// Prepare a photo for the text recognition:
// - cut away the table left and right of the receipt: it otherwise turns into
//   fantasy text (wood grain read as letters), and the receipt gets more pixels
// - scale by the width, so the letters stay large enough (a long receipt must
//   not shrink to tiny print)
// - grayscale
// - adaptive threshold: every pixel is compared with the brightness of its
//   surroundings instead of one value for the whole image, so shadows and
//   uneven light do not turn half of the receipt black
export function prepareImage(bitmap, { crop = true, targetWidth = 1200, adaptive = true, windowFraction = 1 / 16, darkerBy = 0.15 } = {}) {
  const box = (crop && findReceipt(bitmap)) || { x: 0, width: bitmap.width };
  // At most twice the size, and at most 8 million pixels (iPhones refuse very large canvases)
  const scale = Math.min(2, targetWidth / box.width, Math.sqrt(8e6 / (box.width * bitmap.height)));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(box.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, box.x, 0, box.width, bitmap.height, 0, 0, canvas.width, canvas.height);
  if (adaptive) {
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    adaptiveThreshold(image, windowFraction, darkerBy);
    context.putImageData(image, 0, 0);
  }
  return canvas;
}

// Find the receipt's left and right edge: paper is bright and colourless, a table
// usually darker or coloured. Works on a small copy of the photo:
// 1. bright = brighter than Otsu's threshold (the value that separates the
//    brightness histogram best into two groups); paper = bright and not colourful
// 2. the columns where much of the height is paper are the receipt
// Only left and right are cut: top to bottom a shadow could look like the end of
// the receipt and cut off the total. Returns {x, width} (with a small margin) or
// null when the receipt fills the width anyway or no clear receipt was found.
export function findReceipt(bitmap, size = 400) {
  const scale = size / Math.max(bitmap.width, bitmap.height);
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0, w, h);
  const { data } = context.getImageData(0, 0, w, h);

  const gray = new Uint8Array(w * h);
  const colourful = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
    const max = Math.max(r, g, b);
    gray[i] = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
    colourful[i] = max > 0 && (max - Math.min(r, g, b)) / max > 0.3 ? 1 : 0;
  }
  const threshold = otsuThreshold(gray);
  const columns = Array.from({ length: w }, (_, x) => {
    let paper = 0;
    for (let y = 0; y < h; y++) paper += gray[y * w + x] > threshold && !colourful[y * w + x] ? 1 : 0;
    return paper / h;
  });
  const [x1, x2] = longestRun(columns);

  const width = x2 - x1 + 1;
  if (width < 0.15 * w || width > 0.9 * w) return null;
  const margin = 0.04 * width;
  const left = Math.max(0, x1 - margin);
  return { x: left / scale, width: (Math.min(w, x2 + 1 + margin) - left) / scale };
}

function otsuThreshold(gray) {
  const histogram = new Array(256).fill(0);
  gray.forEach((value) => histogram[value]++);
  const total = gray.length;
  const sumAll = histogram.reduce((sum, count, value) => sum + value * count, 0);
  let sumDark = 0, countDark = 0, best = 0, threshold = 128;
  for (let t = 0; t < 256; t++) {
    countDark += histogram[t];
    const countBright = total - countDark;
    if (!countDark || !countBright) continue;
    sumDark += t * histogram[t];
    const meanDark = sumDark / countDark;
    const meanBright = (sumAll - sumDark) / countBright;
    const between = countDark * countBright * (meanDark - meanBright) ** 2;
    if (between > best) {
      best = between;
      threshold = t;
    }
  }
  return threshold;
}

// Longest stretch of values at least half the maximum; small gaps (a fold, a
// dark logo) do not end it. Returns [first index, last index].
function longestRun(values, gapFraction = 0.02) {
  const limit = 0.5 * Math.max(...values);
  const gap = Math.max(1, Math.round(values.length * gapFraction));
  let best = [0, values.length - 1], bestLength = -1, start = -1, last = -1;
  values.forEach((value, i) => {
    if (value < limit) return;
    if (start < 0 || i - last > gap) start = i;
    last = i;
    if (last - start > bestLength) {
      bestLength = last - start;
      best = [start, last];
    }
  });
  return best;
}

// Bradley–Roth adaptive threshold with an integral image (fast enough for phone photos)
function adaptiveThreshold(image, windowFraction, darkerBy) {
  const { width, height, data } = image;
  const gray = new Uint8Array(width * height);
  for (let i = 0; i < gray.length; i++) {
    gray[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
  }
  // integral[y][x] = sum of all gray values above and left of (x, y);
  // whole numbers up to 255 × 8 million pixels fit into 32 bits
  const integral = new Uint32Array((width + 1) * (height + 1));
  for (let y = 0; y < height; y++) {
    let rowSum = 0;
    for (let x = 0; x < width; x++) {
      rowSum += gray[y * width + x];
      integral[(y + 1) * (width + 1) + x + 1] = integral[y * (width + 1) + x + 1] + rowSum;
    }
  }
  const half = Math.max(8, Math.round(width * windowFraction));
  for (let y = 0; y < height; y++) {
    const y1 = Math.max(0, y - half);
    const y2 = Math.min(height, y + half + 1);
    for (let x = 0; x < width; x++) {
      const x1 = Math.max(0, x - half);
      const x2 = Math.min(width, x + half + 1);
      const sum = integral[y2 * (width + 1) + x2] - integral[y1 * (width + 1) + x2]
        - integral[y2 * (width + 1) + x1] + integral[y1 * (width + 1) + x1];
      const mean = sum / ((x2 - x1) * (y2 - y1));
      const value = gray[y * width + x] < mean * (1 - darkerBy) ? 0 : 255;
      const i = (y * width + x) * 4;
      data[i] = data[i + 1] = data[i + 2] = value;
    }
  }
}

// Prices stand right-aligned in one column. Where a reading lost a price
// ("Waschmittel 3, ]"), the price column of that line is read once more on its
// own, with only digits, comma and minus allowed. The column is found from the
// prices that were read with high confidence.
const PRICE = /^-?\d{1,4}[,.]\d{2}$/;
const TOTAL_LINE = /(^|[^a-zäöü])(summe|zu zahlen|gesamt)/i;
let checkingPrices = false; // keeps the progress display quiet during these small readings

async function fillLostPrices(worker, data) {
  const lines = (data.blocks ?? []).flatMap((block) => block.paragraphs.flatMap((p) => p.lines));
  // The image as Tesseract read it (straightened), so the word positions fit
  const image = data.imageGrey && (await createImageBitmap(await (await fetch(data.imageGrey)).blob()));
  const prices = lines
    .flatMap((line) => line.words)
    .filter((w) => PRICE.test(w.text) && w.confidence > 80 && image && w.bbox.x0 > image.width / 2);
  if (prices.length < 2) {
    image?.close();
    return data.text;
  }
  const right = median(prices.map((w) => w.bbox.x1));
  const wide = Math.max(...prices.map((w) => w.bbox.x1 - w.bbox.x0));
  const left = right - 1.5 * wide; // room for "-12,34"
  checkingPrices = true;
  await worker.setParameters({ tessedit_pageseg_mode: "7", tessedit_char_whitelist: "0123456789,-" });
  try {
    const result = [];
    let belowTotal = false; // no items below "Summe" (tax table, card slip): nothing to check there
    for (const line of lines) {
      const text = line.text.trimEnd();
      const inColumn = line.words.filter((w) => w.bbox.x1 > left && w.bbox.x0 < right).map((w) => w.text).join(" ");
      const skip = belowTotal || line.bbox.x1 < left || /\d\s?[,.:]\s?\d\d/.test(inColumn);
      belowTotal ||= TOTAL_LINE.test(text); // the total line itself may still be checked
      if (skip) {
        result.push(text); // nothing in the price column, or a price was read
        continue;
      }
      const pad = 0.2 * (line.bbox.y1 - line.bbox.y0);
      const { data: again } = await worker.recognize(
        crop(image, left - pad, line.bbox.y0 - pad, right + pad, line.bbox.y1 + pad),
        { rotateAuto: false },
      );
      const price = again.text.trim();
      if (!/^-?\d{1,4},\d{2}$/.test(price)) {
        result.push(text);
        continue;
      }
      const before = line.words.filter((w) => w.bbox.x1 <= left + 0.1 * wide).map((w) => w.text).join(" ");
      const after = line.words.filter((w) => w.bbox.x0 >= right - 0.1 * wide).map((w) => w.text).join(" ");
      result.push(`${before}     ${price} ${after}`.trim());
    }
    return result.join("\n");
  } finally {
    checkingPrices = false;
    await worker.setParameters({ tessedit_char_whitelist: "" });
    image.close();
  }
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

// A part of the image, twice as large (small print reads better that way), as a
// PNG data URL: handing Tesseract a canvas makes it call canvas.toBlob(), which
// browsers slow down to about a second per call when the page is in the background
function crop(image, x0, y0, x1, y1, scale = 2) {
  x0 = Math.max(0, x0);
  y0 = Math.max(0, y0);
  x1 = Math.min(image.width, x1);
  y1 = Math.min(image.height, y1);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round((x1 - x0) * scale);
  canvas.height = Math.round((y1 - y0) * scale);
  canvas.getContext("2d").drawImage(image, x0, y0, x1 - x0, y1 - y0, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/png");
}

// Several ways of reading the photo. Each reading loses or misreads other lines,
// so the app reads the photo up to four times and the server combines the
// readings (billbuddy.ml.receipt_ocr.combine): total, store and date by majority,
// the items from the reading whose items add up to the total; up to two items may
// then be taken from other readings if the items then add up to the total exactly.
// Page modes: 4 = one column of text, 6 = one block of text. (3 = automatic
// layout read the prices of a real receipt as a separate column.)
// Width: the receipt scaled to 1200 or 1600 pixels. Which size reads single digits
// right differs from photo to photo, so the second attempt tries the other size.
export const ATTEMPTS = [
  { pageMode: "4", adaptive: true, width: 1200 },
  { pageMode: "4", adaptive: true, width: 1600 },
  { pageMode: "6", adaptive: false, width: 1200 },
  { pageMode: "4", adaptive: false, width: 1200 },
];

// parse: list of texts -> combined receipt (the server). Returns {text, result}.
export async function recognizeReceipt(file, onProgress, parse) {
  onProgress("Texterkennung wird geladen …");
  const Tesseract = await loadTesseract();
  let attempt = 0;
  const worker = await Tesseract.createWorker("deu", 1, {
    logger: (message) => {
      if (message.status === "recognizing text" && !checkingPrices) {
        const round = attempt > 1 ? ` (Versuch ${attempt})` : "";
        onProgress(`Lese Kassenbon${round} … ${Math.round(message.progress * 100)} %`);
      }
    },
  });
  const photo = await loadPhoto(file);
  try {
    onProgress("Bereite das Foto vor …");
    const images = {};
    const texts = [];
    let result;
    for (const { pageMode, adaptive, width } of ATTEMPTS) {
      attempt++;
      const key = `${adaptive}-${width}`;
      images[key] ??= prepareImage(photo, { adaptive, targetWidth: width });
      await worker.setParameters({ tessedit_pageseg_mode: pageMode, preserve_interword_spaces: "1" });
      // rotateAuto straightens slightly tilted photos before reading; blocks = the
      // words with their positions, imageGrey = the straightened image (both for fillLostPrices)
      const { data } = await worker.recognize(images[key], { rotateAuto: true }, { text: true, blocks: true, imageGrey: true });
      onProgress("Prüfe die Preise …");
      texts.push(await fillLostPrices(worker, data));
      result = await parse(texts);
      if (result.items_match_total) break; // the check passed: good enough
    }
    return { text: texts[result.reading ?? 0], result };
  } finally {
    photo.close();
    await worker.terminate();
  }
}

// Who pays how much, from the items assigned to people.
// assignments: item index -> member id, or null for "everyone"; items without a
// person and the difference between items and total are shared equally.
// Returns {memberId: share in cents}.
export function sharesFromItems(items, totalCents, assignments, participantIds) {
  const shares = new Map(participantIds.map((id) => [id, 0]));
  let sharedCents = totalCents;
  items.forEach((item, index) => {
    const memberId = assignments[index];
    const cents = Math.round(item.amount * 100);
    if (memberId == null) return;
    shares.set(memberId, (shares.get(memberId) ?? 0) + cents);
    sharedCents -= cents;
  });
  const everyone = participantIds.length ? participantIds : [...shares.keys()];
  everyone.forEach((id, i) => {
    // Split the shared part exactly to the cent; the first ones get the leftover cents
    const part = Math.floor(sharedCents / everyone.length) + (i < sharedCents % everyone.length ? 1 : 0);
    shares.set(id, shares.get(id) + part);
  });
  return shares;
}

// Shares in cents -> percentages with two decimals that add up to exactly 100
export function percentsFromShares(shares) {
  const total = [...shares.values()].reduce((sum, cents) => sum + cents, 0);
  const entries = [...shares].filter(([, cents]) => cents > 0);
  const percents = new Map(entries.map(([id, cents]) => [id, Math.floor((cents / total) * 10000) / 100]));
  const missing = Math.round((100 - [...percents.values()].reduce((s, p) => s + p, 0)) * 100) / 100;
  const largest = entries.sort((a, b) => b[1] - a[1])[0]?.[0];
  if (largest !== undefined) percents.set(largest, Math.round((percents.get(largest) + missing) * 100) / 100);
  return percents;
}
