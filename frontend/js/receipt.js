// Receipt scan. The text recognition (Tesseract.js) runs on the phone, so the
// photo never leaves the device; only the recognized text goes to the server,
// which finds store, date, total and items (billbuddy.ml.receipt_ocr).

// Loaded only when someone scans for the first time (about 3 MB incl. German language data)
const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js";
let tesseractLoading;

function loadTesseract() {
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

// Phone photos are large; a smaller grayscale image with more contrast is read faster and better
async function prepareImage(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, 1800 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext("2d");
  context.filter = "grayscale(1) contrast(1.4)";
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas;
}

export async function recognizeReceipt(file, onProgress) {
  onProgress("Texterkennung wird geladen …");
  const Tesseract = await loadTesseract();
  const worker = await Tesseract.createWorker("deu", 1, {
    logger: (message) => {
      if (message.status === "recognizing text") onProgress(`Lese Kassenbon … ${Math.round(message.progress * 100)} %`);
    },
  });
  try {
    const { data } = await worker.recognize(await prepareImage(file));
    return data.text;
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
