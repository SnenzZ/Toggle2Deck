const uploadZone = document.getElementById("uploadZone");
const fileInput = document.getElementById("fileInput");
const fileList = document.getElementById("fileList");
const fileListContainer = document.getElementById("fileListContainer");
const fileCount = document.getElementById("fileCount");
const clearAll = document.getElementById("clearAll");
const form = document.querySelector("form");
const colorControls = document.getElementById("colorControls");
const workspace = document.getElementById("workspace");
const globalColor = document.getElementById("globalColor");
const cardRows = document.getElementById("cardRows");
const cardCount = document.getElementById("cardCount");
const cardColors = document.getElementById("cardColors");
const cardCategories = document.getElementById("cardCategories");
const nestedToggle = form.elements.include_nested_toggles;
const categoryName = document.getElementById("categoryName");
const categoryColor = document.getElementById("categoryColor");
const addCategory = document.getElementById("addCategory");
const categoryList = document.getElementById("categoryList");
const categoryCount = document.getElementById("categoryCount");
const categoryFilter = document.getElementById("categoryFilter");

const STORAGE_KEY = "notiontoanki.categories.v1";
const ASSIGNMENT_KEY = "notiontoanki.assignments.v1";
let previewRequest = 0;
let cards = [];
let categories = loadCategories();
let assignments = loadAssignments();
let dragSelection = new Set();
let dragPreview = null;

uploadZone.addEventListener("click", () => fileInput.click());

uploadZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
  uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", (event) => {
  event.preventDefault();
  uploadZone.classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) setFile(file);
});

clearAll.addEventListener("click", clearFile);

nestedToggle.addEventListener("change", () => {
  if (fileInput.files[0]) loadPreview();
});

globalColor.addEventListener("input", syncExportColors);

addCategory.addEventListener("click", addCategoryFromInput);
categoryName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    addCategoryFromInput();
  }
});

function addCategoryFromInput() {
  const name = categoryName.value.trim();
  if (!name) return;
  categories.push({
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`,
    name,
    color: categoryColor.value,
  });
  categoryName.value = "";
  persistCategories();
  renderCategories();
  renderCards();
}

categoryFilter.addEventListener("change", renderCards);

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
    fileList.replaceChildren();
    fileListContainer.classList.add("hidden");
    return;
  }

  fileListContainer.classList.remove("hidden");
  fileCount.textContent = "1 Datei ausgewählt";
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
  cards = [];
  renderFile(null);
  workspace.classList.add("hidden");
  colorControls.classList.add("hidden");
  cardRows.replaceChildren();
  cardColors.value = "{}";
  cardCategories.value = "{}";
}

async function loadPreview() {
  const requestId = ++previewRequest;
  workspace.classList.add("hidden");
  colorControls.classList.add("hidden");
  const data = new FormData();
  data.append("zip_file", fileInput.files[0]);
  if (nestedToggle.checked) data.append("include_nested_toggles", "on");

  try {
    const response = await fetch("/preview", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Vorschau konnte nicht geladen werden.");
    if (requestId !== previewRequest) return;
    cards = payload.cards;
    pruneAssignments();
    renderCategories();
    renderCards();
    workspace.classList.remove("hidden");
    colorControls.classList.remove("hidden");
  } catch (error) {
    if (requestId === previewRequest) alert(error.message);
  }
}

function renderCategories() {
  categoryList.replaceChildren();
  categoryCount.textContent = String(categories.length);

  for (const category of categories) {
    const item = document.createElement("div");
    item.className = "category-chip";
    item.dataset.categoryId = category.id;
    item.style.setProperty("--category", category.color);

    const swatch = document.createElement("span");
    swatch.className = "swatch";

    const name = document.createElement("span");
    name.className = "category-name";
    name.textContent = category.name;

    const controls = document.createElement("span");
    controls.className = "category-actions";

    const color = document.createElement("input");
    color.type = "color";
    color.value = category.color;
    color.setAttribute("aria-label", `Farbe für ${category.name}`);
    color.addEventListener("input", () => {
      category.color = color.value;
      persistCategories();
      renderCategories();
      renderCards();
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-btn";
    remove.setAttribute("aria-label", `${category.name} löschen`);
    remove.textContent = "×";
    remove.addEventListener("click", () => deleteCategory(category.id));

    controls.append(color, remove);
    item.append(swatch, name, controls);
    item.addEventListener("dragover", (event) => {
      if (event.dataTransfer.types.includes("text/card-index")) {
        event.preventDefault();
        item.classList.add("drop-target");
      }
    });
    item.addEventListener("dragleave", () => item.classList.remove("drop-target"));
    item.addEventListener("drop", (event) => {
      event.preventDefault();
      item.classList.remove("drop-target");
      const fallbackIndex = event.dataTransfer.getData("text/card-index");
      const indexes = dragSelection.size ? [...dragSelection] : [fallbackIndex].filter(Boolean);
      assignCardsToCategory(indexes, category.id);
      finishCardDrag();
    });
    categoryList.append(item);
  }

  renderFilterOptions();
}

function renderFilterOptions() {
  const active = categoryFilter.value;
  categoryFilter.replaceChildren(
    new Option("Alle Karten", "all"),
    new Option("Ohne Kategorie", "uncategorized"),
  );
  for (const category of categories) {
    categoryFilter.append(new Option(category.name, category.id));
  }
  categoryFilter.value = [...categoryFilter.options].some((option) => option.value === active)
    ? active
    : "all";
}

function renderCards() {
  cardRows.replaceChildren();
  const visibleCards = cards.filter(matchesFilter);
  cardCount.textContent = `${visibleCards.length} von ${cards.length} Karten`;

  for (const card of visibleCards) {
    cardRows.append(createCardRow(card));
  }
  syncExportColors();
}

function createCardRow(card) {
  const row = document.createElement("article");
  row.className = "card-row";
  row.draggable = true;
  row.dataset.index = card.index;
  row.addEventListener("dragstart", (event) => {
    startCardDrag(event, card.index);
  });
  row.addEventListener("dragenter", () => collectDraggedCard(card.index));
  row.addEventListener("dragover", (event) => {
    if (event.dataTransfer.types.includes("text/card-index")) event.preventDefault();
  });
  row.addEventListener("dragend", finishCardDrag);

  const front = document.createElement("div");
  front.className = "card-front";
  front.textContent = card.front || "(Leere Vorderseite)";

  const category = getCategory(assignments[card.index]);
  const badge = document.createElement("button");
  badge.type = "button";
  badge.className = category ? "card-label" : "card-label empty";
  badge.style.setProperty("--category", category?.color || "#94a3b8");
  badge.textContent = category ? category.name : "Ohne Kategorie";
  badge.addEventListener("click", () => clearAssignment(card.index));

  const select = document.createElement("select");
  select.className = "category-select";
  select.setAttribute("aria-label", `Kategorie für Karte ${card.index + 1}`);
  select.append(new Option("Ohne Kategorie", ""));
  for (const categoryOption of categories) {
    select.append(new Option(categoryOption.name, categoryOption.id));
  }
  select.value = assignments[card.index] || "";
  select.addEventListener("change", () => assignCategory(card.index, select.value));

  row.append(front, badge, select);
  return row;
}

function startCardDrag(event, index) {
  dragSelection = new Set([String(index)]);
  event.dataTransfer.setData("text/card-index", String(index));
  event.dataTransfer.effectAllowed = "move";
  setTransparentDragImage(event);
  document.body.classList.add("dragging-cards");
  markDraggedCards();
  showDragPreview(event);
}

function collectDraggedCard(index) {
  if (!document.body.classList.contains("dragging-cards")) return;
  dragSelection.add(String(index));
  markDraggedCards();
  updateDragPreview();
}

function finishCardDrag() {
  document.body.classList.remove("dragging-cards");
  dragSelection = new Set();
  hideDragPreview();
  markDraggedCards();
  for (const item of categoryList.children) item.classList.remove("drop-target");
}

function markDraggedCards() {
  for (const row of cardRows.children) {
    row.classList.toggle("selected-for-drag", dragSelection.has(row.dataset.index));
  }
}

function setTransparentDragImage(event) {
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  event.dataTransfer.setDragImage(canvas, 0, 0);
}

function showDragPreview(event) {
  hideDragPreview();
  dragPreview = document.createElement("div");
  dragPreview.className = "drag-stack";
  document.body.append(dragPreview);
  updateDragPreview();
  moveDragPreview(event);
}

function updateDragPreview() {
  if (!dragPreview) return;
  const selected = [...dragSelection]
    .map((index) => cards.find((card) => String(card.index) === index))
    .filter(Boolean);
  const count = selected.length;
  const visible = selected.slice(-4);

  dragPreview.replaceChildren();
  for (const [offset, card] of visible.entries()) {
    const layer = document.createElement("div");
    layer.className = "drag-stack-card";
    layer.style.setProperty("--stack-offset", String(offset));
    layer.textContent = card.front || "(Leere Vorderseite)";
    dragPreview.append(layer);
  }

  const counter = document.createElement("div");
  counter.className = "drag-stack-count";
  counter.textContent = `${count} ${count === 1 ? "Karte" : "Karten"}`;
  dragPreview.append(counter);
}

function moveDragPreview(event) {
  if (!dragPreview) return;
  dragPreview.style.left = `${event.clientX + 16}px`;
  dragPreview.style.top = `${event.clientY + 16}px`;
}

function hideDragPreview() {
  if (dragPreview) dragPreview.remove();
  dragPreview = null;
}

document.addEventListener("dragover", moveDragPreview);

function assignCategory(index, categoryId) {
  if (!categoryId) {
    delete assignments[index];
  } else {
    assignments[index] = categoryId;
  }
  persistAssignments();
  renderCards();
}

function assignCardsToCategory(indexes, categoryId) {
  if (!indexes.length) return;
  for (const index of indexes) {
    assignments[index] = categoryId;
  }
  persistAssignments();
  renderCards();
}

function clearAssignment(index) {
  delete assignments[index];
  persistAssignments();
  renderCards();
}

function deleteCategory(categoryId) {
  categories = categories.filter((category) => category.id !== categoryId);
  for (const [index, assignedId] of Object.entries(assignments)) {
    if (assignedId === categoryId) delete assignments[index];
  }
  persistCategories();
  persistAssignments();
  renderCategories();
  renderCards();
}

function syncExportColors() {
  const colorValues = {};
  const categoryValues = {};
  for (const card of cards) {
    const category = getCategory(assignments[card.index]);
    if (category) {
      colorValues[card.index] = category.color;
      categoryValues[card.index] = category.name;
    }
  }
  cardColors.value = JSON.stringify(colorValues);
  cardCategories.value = JSON.stringify(categoryValues);
}

function matchesFilter(card) {
  const filter = categoryFilter.value;
  const assigned = assignments[card.index] || "";
  if (filter === "all") return true;
  if (filter === "uncategorized") return !assigned;
  return assigned === filter;
}

function pruneAssignments() {
  const validIndexes = new Set(cards.map((card) => String(card.index)));
  let changed = false;
  for (const index of Object.keys(assignments)) {
    if (!validIndexes.has(index) || !getCategory(assignments[index])) {
      delete assignments[index];
      changed = true;
    }
  }
  if (changed) persistAssignments();
}

function getCategory(id) {
  return categories.find((category) => category.id === id);
}

function loadCategories() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadAssignments() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ASSIGNMENT_KEY) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function persistCategories() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(categories));
}

function persistAssignments() {
  localStorage.setItem(ASSIGNMENT_KEY, JSON.stringify(assignments));
}

function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

renderCategories();
