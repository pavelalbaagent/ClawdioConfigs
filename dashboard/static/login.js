function byId(id) {
  return document.getElementById(id);
}

function showError(message) {
  const banner = byId("error-banner");
  if (!banner) {
    return;
  }
  if (!message) {
    banner.classList.remove("visible");
    banner.textContent = "";
    return;
  }
  banner.textContent = message;
  banner.classList.add("visible");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function bootstrap() {
  try {
    const status = await api("/api/auth/status");
    const auth = status.auth || {};

    if (auth.required === false) {
      window.location.href = "/";
      return;
    }

    if (auth.authenticated === true) {
      window.location.href = "/";
      return;
    }

    byId("auth-hint").textContent = `Token env key: ${auth.token_env_key || "OPENCLAW_DASHBOARD_TOKEN"}`;
    if (auth.configured === false) {
      showError(
        `Dashboard token is not configured in ${auth.token_env_key || "OPENCLAW_DASHBOARD_TOKEN"}.`
      );
    }
  } catch (error) {
    showError(error.message);
  }
}

async function login() {
  const token = byId("token-input").value.trim();
  if (!token) {
    showError("Token is required.");
    return;
  }

  try {
    await api("/api/auth/login", {
      method: "POST",
      body: { token },
    });
    window.location.href = "/";
  } catch (error) {
    showError(error.message);
  }
}

byId("login-button").addEventListener("click", () => login());
byId("token-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    login();
  }
});

bootstrap();
