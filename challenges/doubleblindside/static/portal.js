(() => {
  const bootstrap = window.portalBootstrap || {};
  const state = {
    currentUser: bootstrap.current_user || null,
    currentRole: bootstrap.current_role || "guest",
  };

  async function apiFetch(url, options = {}) {
    const { data, headers = {}, method = "GET", ...rest } = options;
    const opts = {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...headers,
      },
      ...rest,
    };
    if (data !== undefined) {
      opts.body = JSON.stringify(data);
      opts.headers["Content-Type"] = opts.headers["Content-Type"] || "application/json";
    }

    const response = await fetch(url, opts);
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (_err) {
        payload = { raw: text };
      }
    }
    if (!response.ok) {
      const error = new Error((payload && payload.error) || response.statusText);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function formToJSON(form) {
    const data = new FormData(form);
    const payload = {};
    for (const [key, value] of data.entries()) {
      payload[key] = value.trim ? value.trim() : value;
    }
    return payload;
  }

  function setStatus(node, message, level = "info") {
    if (!node) {
      return;
    }
    if (!message) {
      node.textContent = "";
      node.className = "alert d-none";
      node.hidden = true;
      return;
    }
    node.textContent = message;
    node.className = `alert alert-${level}`;
    node.hidden = false;
  }

  function bindForm(form, handler) {
    if (!form) {
      return;
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      handler(form);
    });
  }

  window.Portal = {
    apiFetch,
    bindForm,
    formToJSON,
    setStatus,
    state,
  };
})();
