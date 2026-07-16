const uploadZone = document.getElementById("uploadZone");
const fileInput = document.getElementById("fileInput");

const fileList = document.getElementById("fileList");
const fileListContainer = document.getElementById("fileListContainer");
const fileCount = document.getElementById("fileCount");
const clearAll = document.getElementById("clearAll");
const form = document.querySelector("form");
const colorControls = document.getElementById("colorControls");
const globalColor = document.getElementById("globalColor");
const cardRows = document.getElementById("cardRows");
const cardCount = document.getElementById("cardCount");
const cardColors = document.getElementById("cardColors");
const nestedToggle = form.elements.include_nested_toggles;
let previewRequest = 0;

uploadZone.addEventListener("click", () => {
  fileInput.click();
});

uploadZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
  uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();

  uploadZone.classList.remove("drag-over");

  const file = e.dataTransfer.files[0];

  if (file) {
    setFile(file);
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];

  if (file) {
    setFile(file);
  }
});

clearAll.addEventListener("click", () => {
  clearFile();
});

function setFile(file) {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    alert("Bitte eine ZIP-Datei auswählen.");
    return;
  }

  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;

  renderFile(file);
  loadPreview();
}

function renderFile(file) {
  if (!file) {
    fileList.innerHTML = "";
    fileListContainer.classList.add("hidden");
    return;
  }

  fileListContainer.classList.remove("hidden");

  fileCount.textContent = "1 file selected";
  fileList.replaceChildren(createFileItem(file));
}

function createFileItem(file) {
  const item = document.createElement("div");
  item.className = "file-item";

  const info = document.createElement("div");
  info.className = "file-info";

  const name = document.createElement("div");
  name.className = "file-name";
  name.textContent = file.name;

  const size = document.createElement("div");
  size.className = "file-size";
  size.textContent = formatFileSize(file.size);

  info.append(name, size);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-btn";
  remove.setAttribute("aria-label", "Datei entfernen");
  remove.textContent = "×";
  remove.addEventListener("click", clearFile);

  item.append(info, remove);
  return item;
}

function clearFile() {
  fileInput.value = "";
  renderFile(null);
  colorControls.classList.add("hidden");
  cardRows.replaceChildren();
  cardColors.value = "{}";
}

nestedToggle.addEventListener("change", () => {
  if (fileInput.files[0]) loadPreview();
});

async function loadPreview() {
  const requestId = ++previewRequest;
  colorControls.classList.add("hidden");
  const data = new FormData();
  data.append("zip_file", fileInput.files[0]);
  if (nestedToggle.checked) data.append("include_nested_toggles", "on");

  try {
    const response = await fetch("/preview", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Vorschau konnte nicht geladen werden.");
    if (requestId !== previewRequest) return;
    renderCards(payload.cards);
  } catch (error) {
    if (requestId === previewRequest) alert(error.message);
  }
}

function renderCards(cards) {
  cardRows.replaceChildren();
  cardCount.textContent = `${cards.length} Karten`;
  for (const card of cards) cardRows.append(createCardRow(card));
  cardColors.value = "{}";
  colorControls.classList.remove("hidden");
}

function createCardRow(card) {
  const row = document.createElement("div");
  row.className = "card-row";
  row.dataset.index = card.index;

  const front = document.createElement("div");
  front.className = "card-front";
  front.textContent = card.front || "(Leere Vorderseite)";

  const overrideLabel = document.createElement("label");
  overrideLabel.className = "override-color";
  const override = document.createElement("input");
  override.type = "checkbox";
  override.setAttribute("aria-label", `Eigene Farbe für Karte ${card.index + 1}`);
  const picker = document.createElement("input");
  picker.type = "color";
  picker.value = globalColor.value;
  picker.disabled = true;
  picker.setAttribute("aria-label", `Farbe für Karte ${card.index + 1}`);
  const copy = document.createElement("span");
  copy.textContent = "Eigene Farbe";
  overrideLabel.append(override, copy, picker);

  override.addEventListener("change", () => {
    picker.disabled = !override.checked;
    updateCardColors();
  });
  picker.addEventListener("input", updateCardColors);
  row.append(front, overrideLabel);
  return row;
}

globalColor.addEventListener("input", () => {
  for (const row of cardRows.children) {
    const override = row.querySelector('input[type="checkbox"]');
    if (!override.checked) row.querySelector('input[type="color"]').value = globalColor.value;
  }
});

function updateCardColors() {
  const values = {};
  for (const row of cardRows.children) {
    const override = row.querySelector('input[type="checkbox"]');
    if (override.checked) values[row.dataset.index] = row.querySelector('input[type="color"]').value;
  }
  cardColors.value = JSON.stringify(values);
}

function formatFileSize(bytes) {
  if (bytes === 0) {
    return "0 Bytes";
  }

  const k = 1024;

  const sizes = ["Bytes", "KB", "MB", "GB"];

  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(k)),
    sizes.length - 1,
  );

  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}
