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

// Prepare a photo for the text recognition:
// - scale by the width, so the letters stay large enough (a long receipt must
//   not shrink to tiny print)
// - grayscale
// - adaptive threshold: every pixel is compared with the brightness of its
//   surroundings instead of one value for the whole image, so shadows and
//   uneven light do not turn half of the receipt black
export async function prepareImage(file, { maxWidth = 2000, adaptive = true, windowFraction = 1 / 16, darkerBy = 0.15 } = {}) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxWidth / bitmap.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  if (adaptive) {
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    adaptiveThreshold(image, windowFraction, darkerBy);
    context.putImageData(image, 0, 0);
  }
  return canvas;
}

// Bradley–Roth adaptive threshold with an integral image (fast enough for phone photos)
function adaptiveThreshold(image, windowFraction, darkerBy) {
  const { width, height, data } = image;
  const gray = new Float32Array(width * height);
  for (let i = 0; i < gray.length; i++) {
    gray[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
  }
  // integral[y][x] = sum of all gray values above and left of (x, y)
  const integral = new Float64Array((width + 1) * (height + 1));
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

// Several ways of reading the photo. No single setting was best for all test
// photos, so the app tries them one after another and keeps the most plausible
// result – judged by the parser's own check (do the items add up to the total?).
// Page modes: 4 = one column of text, 3 = automatic layout, 6 = one block of text.
const ATTEMPTS = [
  { pageMode: "4", adaptive: true },
  { pageMode: "3", adaptive: true },
  { pageMode: "6", adaptive: false },
];

function plausibility(result) {
  return (result.items_match_total ? 100 : 0) + (result.total ? 10 : 0) + (result.store ? 5 : 0)
    + (result.date ? 3 : 0) + result.items.length;
}

// parse: text -> parsed receipt (the server). Returns {text, result} of the best attempt.
export async function recognizeReceipt(file, onProgress, parse) {
  onProgress("Texterkennung wird geladen …");
  const Tesseract = await loadTesseract();
  let attempt = 0;
  const worker = await Tesseract.createWorker("deu", 1, {
    logger: (message) => {
      if (message.status === "recognizing text") {
        const round = attempt > 1 ? ` (Versuch ${attempt})` : "";
        onProgress(`Lese Kassenbon${round} … ${Math.round(message.progress * 100)} %`);
      }
    },
  });
  try {
    onProgress("Bereite das Foto vor …");
    const images = {};
    let best = null;
    for (const { pageMode, adaptive } of ATTEMPTS) {
      attempt++;
      images[adaptive] ??= await prepareImage(file, { adaptive });
      await worker.setParameters({ tessedit_pageseg_mode: pageMode, preserve_interword_spaces: "1" });
      // rotateAuto straightens slightly tilted photos before reading
      const { data } = await worker.recognize(images[adaptive], { rotateAuto: true });
      const result = await parse(data.text);
      if (!best || plausibility(result) > plausibility(best.result)) best = { text: data.text, result };
      if (result.items_match_total) break; // the check passed: good enough
    }
    return best;
  } finally {
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
