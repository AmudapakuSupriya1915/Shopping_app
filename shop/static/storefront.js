"use strict";

const $ = (selector) => document.querySelector(selector);
const money = (cents) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
const icon = (name) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const icons = () => globalThis.lucide?.createIcons();
const state = {
  products: [], user: null, cart: { items: [], total_cents: 0 }, category: "", savedOnly: false,
  favorites: new Set(), token: null, authMode: "login", afterLogin: null, busy: false,
  checkoutAttempt: null, toastTimer: null, ordersOffset: 0, orderPages: [],
};

try {
  state.token = sessionStorage.getItem("forme-token");
  const saved = JSON.parse(localStorage.getItem("forme-saved") || "[]");
  if (Array.isArray(saved)) state.favorites = new Set(saved.filter(Number.isInteger));
} catch {}

const productMedia = {
  "ELEC-KB-001": { image: "keyboard.jpg", description: "A tactile companion for focused mornings and ideas that run late. A little intention for your everyday workspace." },
  "ELEC-MS-001": { image: "mouse.jpg", description: "A clean, considered addition to your desk. Keep your everyday setup simple, comfortable, and ready to go." },
  "ELEC-HP-001": { image: "headphones.jpg", description: "Make a little room for your own rhythm. An everyday companion for your commute, your workspace, and your downtime." },
  "HOME-BT-001": { image: "bottle.jpg", description: "From the first meeting to the last mile. A refillable essential to keep close, wherever the day takes you." },
  "BAGS-LP-001": { image: "backpack.jpg", description: "Bring the essentials, leave the rest. A practical everyday carry for the journey between work and whatever comes next." },
};
const media = (product) => productMedia[product.sku] || { image: "workspace.jpg", description: "A considered addition to your everyday rotation. Selected for the little moments that make up your day." };
const productById = (id) => state.products.find((product) => product.id === Number(id));

function saveToken(token) {
  state.token = token;
  try { token ? sessionStorage.setItem("forme-token", token) : sessionStorage.removeItem("forme-token"); } catch {}
}

function resetAccount() {
  saveToken(null);
  state.user = null;
  state.cart = { items: [], total_cents: 0 };
  state.checkoutAttempt = null;
  state.orderPages = [];
  updateHeader();
  renderBag();
}

async function api(path, { method = "GET", data, headers = {}, authenticate = true } = {}) {
  const requestHeaders = { ...headers };
  if (data !== undefined) requestHeaders["Content-Type"] = "application/json";
  if (authenticate && state.token) requestHeaders.Authorization = `Bearer ${state.token}`;
  let response;
  try {
    response = await fetch(`/api${path}`, { method, headers: requestHeaders, body: data === undefined ? undefined : JSON.stringify(data) });
  } catch { throw new Error("We couldn't connect. Check your connection and try again."); }
  const result = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && authenticate && state.token) {
      resetAccount();
      if ($("#bag-dialog").open) $("#bag-dialog").close();
      if ($("#orders-dialog").open) $("#orders-dialog").close();
    }
    throw new Error(result?.error?.message || "Something went wrong. Please try again.");
  }
  return result;
}

function toast(message) {
  clearTimeout(state.toastTimer);
  $("#toast-message").textContent = message;
  $("#toast").hidden = false;
  state.toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 5000);
}

function showDialog(id) {
  const dialog = $(`#${id}`);
  if (!dialog.open) dialog.showModal();
}

function updateHeader() {
  const count = state.cart.items.reduce((total, item) => total + item.quantity, 0);
  $("#bag-count").textContent = count;
  $('[data-action="bag"]').setAttribute("aria-label", `Open shopping bag, ${count} items`);
  $("#saved-count").textContent = state.favorites.size ? `(${state.favorites.size})` : "";
  $("#account-button").setAttribute("aria-label", state.user ? `Account for ${state.user.name}` : "Sign in");
  $("#account-button").title = state.user ? state.user.name : "Sign in";
}

function emptyState(symbol, title, description, button = "") {
  return `<div class="empty-state">${icon(symbol)}<h3>${escapeHTML(title)}</h3><p>${escapeHTML(description)}</p>${button}</div>`;
}

function renderCategories() {
  const categories = [...new Set(state.products.map((product) => product.category))];
  $("#category-tabs").innerHTML = ["", ...categories].map((category) => `<button class="category-tab ${state.category === category ? "selected" : ""}" data-category="${escapeHTML(category)}" aria-pressed="${state.category === category}">${escapeHTML(category || "All essentials")}</button>`).join("");
}

function renderProducts() {
  const query = $("#search").value.trim().toLowerCase();
  let products = state.products.filter((product) =>
    (!state.category || product.category === state.category) &&
    (!state.savedOnly || state.favorites.has(product.id)) &&
    `${product.name} ${product.category} ${product.sku}`.toLowerCase().includes(query));
  const sort = $("#sort").value;
  if (sort === "price-low") products.sort((first, second) => first.price_cents - second.price_cents);
  if (sort === "price-high") products.sort((first, second) => second.price_cents - first.price_cents);
  if (sort === "name") products.sort((first, second) => first.name.localeCompare(second.name));
  $("#catalog-title").innerHTML = state.savedOnly ? "Your considered collection<span>.</span>" : "Find your next favorite<span>.</span>";
  $("#collection-count").textContent = `${products.length} ${products.length === 1 ? "essential" : "essentials"}`;
  $("#product-grid").setAttribute("aria-busy", "false");
  if (!products.length) {
    $("#product-grid").innerHTML = emptyState(state.savedOnly ? "heart" : "search", state.savedOnly ? "A space for your favorites." : "Nothing here just yet.", state.savedOnly ? "Save the things you love. They'll be waiting right here." : "Try another search or category.", '<button class="secondary-button" data-action="reset-filters">Browse all essentials</button>');
    icons();
    return;
  }
  $("#product-grid").innerHTML = products.map((product) => {
    const saved = state.favorites.has(product.id);
    return `<article class="product-card">
      <div class="product-visual"><button class="product-open" data-action="product" data-id="${product.id}" aria-label="View ${escapeHTML(product.name)}"><img class="product-image" src="/static/${media(product).image}" alt="${escapeHTML(product.name)}" loading="lazy" width="500" height="450"></button>
      ${product.stock === 0 ? '<span class="product-tag">Out of stock</span>' : product.stock <= 5 ? '<span class="product-tag">Last few</span>' : product.sku === "ELEC-KB-001" ? '<span class="product-tag">The desk edit</span>' : ""}
      <button class="icon-button save-button ${saved ? "saved" : ""}" data-action="favorite" data-id="${product.id}" aria-label="${saved ? "Unsave" : "Save"} ${escapeHTML(product.name)}" aria-pressed="${saved}" title="${saved ? "Remove from saved" : "Save for later"}">${icon("heart")}</button></div>
      <p class="product-category">${escapeHTML(product.category)}</p><h3><button class="product-title" data-action="product" data-id="${product.id}">${escapeHTML(product.name)}</button></h3>
      <div class="product-bottom"><span class="price">${money(product.price_cents)}</span><button class="add-button" data-action="add" data-id="${product.id}" ${!product.stock || state.busy ? "disabled" : ""}>${icon("plus")} ${product.stock ? "Add to bag" : "Sold out"}</button></div></article>`;
  }).join("");
  icons();
}

async function loadProducts() {
  const products = [];
  let offset = 0;
  while (true) {
    const result = await api(`/products?limit=100&offset=${offset}`, { authenticate: false });
    products.push(...result.items);
    if (result.items.length < 100) break;
    offset += 100;
  }
  state.products = products;
  renderCategories();
  renderProducts();
}

function setView(savedOnly) {
  state.savedOnly = savedOnly;
  document.querySelectorAll(".main-nav .nav-link").forEach((button) => {
    const active = button.dataset.action === (savedOnly ? "saved" : "shop");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  renderProducts();
}

function toggleFavorite(id) {
  id = Number(id);
  if (state.favorites.has(id)) state.favorites.delete(id);
  else state.favorites.add(id);
  try { localStorage.setItem("forme-saved", JSON.stringify([...state.favorites])); } catch {}
  renderProducts();
  updateHeader();
}

function showProduct(id) {
  const product = productById(id);
  if (!product) return;
  $("#product-detail").innerHTML = `<img class="detail-image" src="/static/${media(product).image}" alt="${escapeHTML(product.name)}"><div class="detail-copy"><p class="eyebrow">${escapeHTML(product.category.toUpperCase())}</p><h2 id="product-title">${escapeHTML(product.name)}</h2><p class="price">${money(product.price_cents)}</p><p class="stock-note"><span class="live-dot"></span>${product.stock ? `${product.stock} in stock` : "Currently out of stock"}</p><p class="detail-description">${escapeHTML(media(product).description)}</p><button class="primary-button full-width" data-action="add" data-id="${product.id}" ${!product.stock || state.busy ? "disabled" : ""}>${product.stock ? "Add to bag" : "Sold out"} ${icon("shopping-bag")}</button><p class="detail-sku">SKU / ${escapeHTML(product.sku)}</p></div>`;
  icons();
  showDialog("product-dialog");
}

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === "register";
  $("#name-field").hidden = !registering;
  $('[name="name"]').required = registering;
  $("#password-hint").hidden = !registering;
  $("#password").minLength = registering ? 12 : 1;
  $("#password").autocomplete = registering ? "new-password" : "current-password";
  $("#auth-title").textContent = registering ? "Make yourself at home." : "Good to see you.";
  $("#auth-subtitle").textContent = registering ? "A few details, and you're part of the everyday." : "Your favorites, your bag, your everyday.";
  $("#auth-submit").innerHTML = `${registering ? "Create account" : "Sign in"} ${icon("arrow-right")}`;
  $("#auth-error").hidden = true;
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    const selected = button.dataset.authMode === mode;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected);
  });
  icons();
}

function requireAccount(callback) {
  if (state.user) { callback(); return; }
  state.afterLogin = callback;
  if ($("#product-dialog").open) $("#product-dialog").close();
  setAuthMode("login");
  showDialog("auth-dialog");
}

async function submitAuth(event) {
  event.preventDefault();
  const submit = $("#auth-submit");
  submit.disabled = true;
  $("#auth-error").hidden = true;
  const form = new FormData(event.currentTarget);
  const credentials = { email: form.get("email"), password: form.get("password") };
  try {
    if (state.authMode === "register") {
      await api("/auth/register", { method: "POST", data: { ...credentials, name: form.get("name") }, authenticate: false });
      setAuthMode("login");
    }
    const session = await api("/auth/login", { method: "POST", data: credentials, authenticate: false });
    saveToken(session.access_token);
    state.user = await api("/auth/me");
    state.cart = await api("/cart");
    updateHeader();
    $("#auth-dialog").close();
    $("#auth-form").reset();
    toast(`Welcome, ${state.user.name.split(" ")[0]}.`);
    const callback = state.afterLogin;
    state.afterLogin = null;
    if (callback) await callback();
  } catch (error) {
    $("#auth-error").textContent = error.message;
    $("#auth-error").hidden = false;
  } finally { submit.disabled = false; }
}

async function refreshCart() {
  state.cart = await api("/cart");
  updateHeader();
  renderBag();
}

async function changeCart(id, quantity) {
  if (state.busy) return;
  state.busy = true;
  renderProducts();
  renderBag();
  try {
    if (quantity <= 0) {
      await api(`/cart/items/${id}`, { method: "DELETE" });
      state.cart = await api("/cart");
    } else state.cart = await api(`/cart/items/${id}`, { method: "PUT", data: { quantity } });
    state.checkoutAttempt = null;
    updateHeader();
  } finally {
    state.busy = false;
    renderProducts();
    renderBag();
  }
}

async function addToBag(id) {
  requireAccount(async () => {
    try {
      const current = state.cart.items.find((item) => item.product_id === Number(id));
      await changeCart(Number(id), (current?.quantity || 0) + 1);
      if ($("#product-dialog").open) $("#product-dialog").close();
      toast("A good choice. Added to your bag.");
    } catch (error) { toast(error.message); }
  });
}

function renderBag() {
  const items = state.cart.items;
  $("#bag-summary").hidden = !items.length;
  $("#checkout-button").disabled = state.busy;
  if (!items.length) {
    $("#bag-items").innerHTML = emptyState("shopping-bag", "Room for something good.", "Your everyday essentials are waiting to be discovered.", '<button class="primary-button" data-action="continue-shopping">Explore the collection</button>');
  } else {
    $("#bag-items").innerHTML = items.map((item) => `<article class="bag-item"><img class="bag-item-image" src="/static/${media(item).image}" alt="${escapeHTML(item.name)}" width="83" height="90"><div class="bag-item-info"><h3>${escapeHTML(item.name)}</h3><p class="price">${money(item.price_cents * item.quantity)}</p><div class="bag-item-controls"><div class="stepper" aria-label="Quantity for ${escapeHTML(item.name)}"><button data-action="quantity" data-id="${item.product_id}" data-quantity="${item.quantity - 1}" aria-label="Decrease ${escapeHTML(item.name)} quantity" title="Decrease quantity" ${state.busy ? "disabled" : ""}>${icon("minus")}</button><span>${item.quantity}</span><button data-action="quantity" data-id="${item.product_id}" data-quantity="${item.quantity + 1}" aria-label="Increase ${escapeHTML(item.name)} quantity" title="Increase quantity" ${state.busy || item.quantity >= item.stock || item.quantity >= 1000 ? "disabled" : ""}>${icon("plus")}</button></div><button class="remove-button" data-action="remove" data-id="${item.product_id}" ${state.busy ? "disabled" : ""}>Remove</button></div></div></article>`).join("");
  }
  $("#bag-total").textContent = money(state.cart.total_cents);
  icons();
}

async function openBag() {
  renderBag();
  showDialog("bag-dialog");
  try { await refreshCart(); } catch (error) { toast(error.message); }
}

async function checkout(event) {
  event.preventDefault();
  if (state.busy) return;
  const address = new FormData(event.currentTarget).get("address").trim();
  if (!state.checkoutAttempt || state.checkoutAttempt.address !== address) {
    state.checkoutAttempt = { key: crypto.randomUUID(), address };
  }
  state.busy = true;
  $("#checkout-error").hidden = true;
  renderBag();
  $("#checkout-button").textContent = "Placing your order...";
  try {
    const order = await api("/orders", { method: "POST", data: { shipping_address: address }, headers: { "Idempotency-Key": state.checkoutAttempt.key } });
    state.checkoutAttempt = null;
    state.cart = { items: [], total_cents: 0 };
    updateHeader();
    $("#bag-dialog").close();
    $("#checkout-form").reset();
    toast(`Order #${String(order.id).padStart(4, "0")} placed. A good day for good things.`);
    await loadProducts();
    await openOrders();
  } catch (error) {
    $("#checkout-error").textContent = error.message;
    $("#checkout-error").hidden = false;
  } finally {
    state.busy = false;
    $("#checkout-button").innerHTML = `Place order ${icon("arrow-right")}`;
    renderProducts();
    renderBag();
  }
}

async function openOrders(append = false) {
  showDialog("orders-dialog");
  if (!append) {
    state.ordersOffset = 0;
    state.orderPages = [];
    $("#orders-list").innerHTML = '<div class="empty-state"><span class="loader"></span><p>Finding your orders...</p></div>';
  }
  try {
    const result = await api(`/orders?limit=20&offset=${state.ordersOffset}`);
    const detailed = await Promise.all(result.items.map((order) => api(`/orders/${order.id}`)));
    state.orderPages.push(...detailed);
    state.ordersOffset += result.items.length;
    if (!state.orderPages.length) {
      $("#orders-list").innerHTML = emptyState("package", "Good things are on the horizon.", "Your orders will find a home here.", '<button class="primary-button" data-action="continue-shopping">Explore the collection</button>');
    } else {
      $("#orders-list").innerHTML = state.orderPages.map((order) => {
        const date = new Date(`${order.created_at.replace(" ", "T")}Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        return `<article class="order-row"><div class="order-heading"><div><h3>Order #${String(order.id).padStart(4, "0")}</h3><p class="order-date">${date}</p></div><span class="status ${order.status}">${escapeHTML(order.status)}</span></div><div class="order-lines">${order.items.map((item) => `<div class="order-line"><span>${escapeHTML(item.product_name)} &times; ${item.quantity}</span><span>${money(item.unit_price_cents * item.quantity)}</span></div>`).join("")}</div><div class="order-total"><span>Order total</span><strong>${money(order.total_cents)}</strong></div><p class="order-address">${escapeHTML(order.shipping_address)}</p>${order.status === "placed" ? `<button class="cancel-order" data-action="cancel-order" data-id="${order.id}">Cancel order</button>` : ""}</article>`;
      }).join("") + (result.items.length === 20 ? '<button class="secondary-button full-width" data-action="more-orders">Load more orders</button>' : "");
    }
  } catch (error) {
    $("#orders-list").innerHTML = emptyState("wifi-off", "Couldn't load your orders.", error.message, '<button class="secondary-button" data-action="orders">Try again</button>');
  }
  icons();
}

async function cancelOrder(id, button) {
  if (!confirm(`Cancel order #${String(id).padStart(4, "0")}? Its items will be returned to stock.`)) return;
  button.disabled = true;
  try {
    await api(`/orders/${id}/cancel`, { method: "POST" });
    toast("Order cancelled. Items have been returned to stock.");
    await openOrders();
    await loadProducts();
  } catch (error) { toast(error.message); button.disabled = false; }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  if (button.dataset.close) { $(`#${button.dataset.close}`).close(); return; }
  if (button.dataset.category !== undefined) {
    state.category = button.dataset.category;
    renderCategories(); renderProducts(); return;
  }
  if (button.dataset.authMode) { setAuthMode(button.dataset.authMode); return; }
  const { action, id } = button.dataset;
  try {
    if (action === "shop" || action === "saved") { setView(action === "saved"); $("#catalog").scrollIntoView({ behavior: "smooth" }); }
    if (action === "explore") { setView(false); $("#catalog").scrollIntoView({ behavior: "smooth" }); }
    if (action === "reset-filters") { state.category = ""; $("#search").value = ""; setView(false); renderCategories(); }
    if (action === "favorite") toggleFavorite(id);
    if (action === "product") showProduct(id);
    if (action === "add") await addToBag(id);
    if (action === "bag") requireAccount(openBag);
    if (action === "orders" || action === "account-orders") { $("#account-dialog").close(); requireAccount(openOrders); }
    if (action === "account") {
      if (state.user) {
        $("#account-title").textContent = `Hello, ${state.user.name.split(" ")[0]}.`;
        $("#account-email").textContent = state.user.email;
        showDialog("account-dialog");
      } else requireAccount(() => {});
    }
    if (action === "password") {
      const show = $("#password").type === "password";
      $("#password").type = show ? "text" : "password";
      button.innerHTML = icon(show ? "eye-off" : "eye");
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.title = show ? "Hide password" : "Show password";
      icons();
    }
    if (action === "logout") {
      button.disabled = true;
      try { await api("/auth/logout", { method: "POST" }); resetAccount(); $("#account-dialog").close(); toast("You're signed out. See you soon."); }
      finally { button.disabled = false; }
    }
    if (action === "quantity" || action === "remove") await changeCart(Number(id), action === "remove" ? 0 : Number(button.dataset.quantity));
    if (action === "continue-shopping") { document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close()); $("#catalog").scrollIntoView({ behavior: "smooth" }); }
    if (action === "cancel-order") await cancelOrder(id, button);
    if (action === "more-orders") { button.disabled = true; await openOrders(true); }
    if (action === "dismiss-toast") $("#toast").hidden = true;
    if (action === "top") window.scrollTo({ top: 0, behavior: "smooth" });
    if (action === "retry") await loadProducts();
  } catch (error) { toast(error.message); }
});

$("#auth-form").addEventListener("submit", submitAuth);
$("#checkout-form").addEventListener("submit", checkout);
$("#search").addEventListener("input", renderProducts);
$("#sort").addEventListener("change", renderProducts);
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
  });
  dialog.addEventListener("close", () => { if (dialog.id === "auth-dialog") state.afterLogin = null; });
});

async function initialize() {
  icons();
  updateHeader();
  try { await loadProducts(); }
  catch (error) {
    $("#product-grid").setAttribute("aria-busy", "false");
    $("#collection-count").textContent = "Collection unavailable";
    $("#product-grid").innerHTML = emptyState("wifi-off", "A brief pause.", error.message, '<button class="secondary-button" data-action="retry">Try again</button>');
    icons();
  }
  if (state.token) {
    try { state.user = await api("/auth/me"); await refreshCart(); }
    catch (error) { resetAccount(); toast(error.message); }
  }
}

initialize();