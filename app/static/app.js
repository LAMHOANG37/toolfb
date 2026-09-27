document.querySelectorAll("form").forEach(form => {
  form.addEventListener("submit", event => {
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) { event.preventDefault(); return; }
    if ((form.method || "get").toLowerCase() === "get") {
      form.querySelectorAll("select").forEach(el => { if (!el.value) el.disabled = true; });
    }
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(button => {
      button.disabled = true; button.dataset.original = button.textContent; button.textContent = "Đang xử lý…";
    });
  });
});
window.addEventListener("pageshow", () => {
  document.querySelectorAll("button[data-original]").forEach(b => { b.disabled = false; b.textContent = b.dataset.original; });
  document.querySelectorAll("select:disabled").forEach(s => s.disabled = false);
});
document.querySelectorAll("[data-back]").forEach(button => button.addEventListener("click", () => history.back()));
const indicator = document.querySelector("[data-operation]");
if (indicator) {
  let failures = 0;
  const poll = async () => {
    try {
      const response = await fetch("/api/operations/" + encodeURIComponent(indicator.dataset.operation), {headers: {Accept: "application/json"}});
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) throw new Error();
      const operation = await response.json();
      indicator.textContent = operation.detail || "Đang xử lý tác vụ…";
      if (["completed", "partial"].includes(operation.status)) {
        const url = new URL(location.href); url.searchParams.delete("operation");
        location.replace(url.toString()); return;
      }
      if (operation.status === "failed") { indicator.classList.add("error"); return; }
      failures = 0; setTimeout(poll, 2500);
    } catch {
      failures += 1; indicator.textContent = "Chưa lấy được trạng thái. Đang thử kết nối lại…";
      if (failures < 5) setTimeout(poll, 5000);
      else indicator.textContent = "Mất kết nối. Tải lại trang để kiểm tra tác vụ.";
    }
  };
  poll();
}
