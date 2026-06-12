const uploadZone = document.getElementById("uploadZone");
const fileInput = document.getElementById("fileInput");

const fileList = document.getElementById("fileList");
const fileListContainer = document.getElementById("fileListContainer");
const fileCount = document.getElementById("fileCount");
const clearAll = document.getElementById("clearAll");

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
