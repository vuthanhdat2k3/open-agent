const { invoke } = window.__TAURI__.core;

window.addEventListener("DOMContentLoaded", async () => {
  const input = document.querySelector("#server-url-input");
  const errorMsg = document.querySelector("#error-msg");
  const button = document.querySelector("#connect-btn");
  const buttonLabel = button.querySelector(".btn-label");
  const savedUrl = await invoke("get_server_url");
  if (savedUrl) input.value = savedUrl;

  document.querySelector("#connect-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    errorMsg.textContent = "";
    button.disabled = true;
    buttonLabel.textContent = "Đang kết nối...";
    try {
      await invoke("save_server_url", { url: input.value });
    } catch (err) {
      errorMsg.textContent = err;
      button.disabled = false;
      buttonLabel.textContent = "Kết nối";
    }
  });
});
