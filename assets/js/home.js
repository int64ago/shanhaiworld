const catalogUrl = new URL("../data/collections.json", import.meta.url);
const grid = document.querySelector("#collection-grid");
const emptyState = document.querySelector("#empty-state");
const count = document.querySelector("#collection-count");

function createCard(item, index) {
  const card = document.createElement("a");
  card.className = "collection-card";
  card.href = item.href;
  card.style.setProperty("--card-index", index);
  card.setAttribute("aria-label", `进入${item.name}的 3D 场景`);

  const media = document.createElement("div");
  media.className = "collection-card-media";

  if (item.preview) {
    const image = document.createElement("img");
    image.src = item.preview;
    image.alt = `${item.name}预览`;
    image.loading = "lazy";
    image.addEventListener("error", () => media.classList.add("is-fallback"));
    media.append(image);
  } else {
    media.classList.add("is-fallback");
  }

  const ordinal = document.createElement("span");
  ordinal.className = "collection-ordinal";
  ordinal.textContent = String(index + 1).padStart(2, "0");
  media.append(ordinal);

  const content = document.createElement("div");
  content.className = "collection-card-content";
  const heading = document.createElement("div");
  const subtitle = document.createElement("p");
  subtitle.textContent = item.subtitle || item.body_type || "山海神兽";
  const name = document.createElement("h3");
  name.textContent = item.name;
  heading.append(subtitle, name);

  const arrow = document.createElement("span");
  arrow.className = "card-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "↗";
  content.append(heading, arrow);

  if (item.summary) {
    const summary = document.createElement("p");
    summary.className = "collection-summary";
    summary.textContent = item.summary;
    content.append(summary);
  }

  card.append(media, content);
  return card;
}

async function loadCatalog() {
  try {
    const response = await fetch(catalogUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`目录加载失败（${response.status}）`);

    const payload = await response.json();
    const items = Array.isArray(payload.collections)
      ? payload.collections.filter((item) => item.status === "ready" && item.href)
      : [];

    count.textContent = String(items.length);
    emptyState.hidden = items.length !== 0;
    grid.replaceChildren(...items.map(createCard));
  } catch (error) {
    emptyState.hidden = false;
    emptyState.querySelector("h3").textContent = "图鉴暂时无法加载";
    emptyState.querySelector("p").textContent = error.message;
  }
}

loadCatalog();
