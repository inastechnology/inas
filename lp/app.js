(() => {
  "use strict";

  const config = window.INAS_LP_CONFIG ?? {};
  const attributionKeys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid"];
  const campaignStorageKey = "inas-lp-attribution-v1";
  const params = new URLSearchParams(window.location.search);

  const readStoredAttribution = () => {
    try {
      return JSON.parse(window.sessionStorage.getItem(campaignStorageKey) || "{}") ?? {};
    } catch {
      return {};
    }
  };

  const attribution = { ...readStoredAttribution() };
  attributionKeys.forEach((key) => {
    const value = params.get(key)?.trim();
    if (value) attribution[key] = value.slice(0, 300);
  });
  attribution.landing_path = `${window.location.pathname}${window.location.search}`.slice(0, 1000);
  attribution.referrer_host = (() => {
    try { return document.referrer ? new URL(document.referrer).hostname : ""; } catch { return ""; }
  })();
  try { window.sessionStorage.setItem(campaignStorageKey, JSON.stringify(attribution)); } catch { /* Session storage is optional. */ }

  const validGaId = typeof config.analyticsMeasurementId === "string" && /^G-[A-Z0-9]+$/.test(config.analyticsMeasurementId);
  if (validGaId) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function gtag() { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", config.analyticsMeasurementId, { anonymize_ip: true });
    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(config.analyticsMeasurementId)}`;
    document.head.append(script);
  }

  const selectedAudience = () => document.querySelector('[data-audience][aria-selected="true"]')?.dataset.audience || "home";
  const track = (name, details = {}) => {
    const safeDetails = { ...details, audience: selectedAudience(), ...attribution };
    window.dispatchEvent(new CustomEvent("inas:conversion", { detail: { event: name, ...safeDetails } }));
    if (Array.isArray(window.dataLayer)) window.dataLayer.push({ event: name, ...safeDetails });
    if (typeof window.gtag === "function") window.gtag("event", name, safeDetails);
    if (typeof window.fbq === "function") window.fbq("trackCustom", name, safeDetails);
  };

  const publicLinkKeys = { official: "officialSiteUrl", github: "githubUrl", instagram: "instagramUrl", privacy: "privacyUrl" };
  document.querySelectorAll("[data-config-link]").forEach((link) => {
    const key = publicLinkKeys[link.dataset.configLink];
    if (config[key]) link.href = config[key];
  });
  document.querySelectorAll("[data-track]").forEach((element) => {
    element.addEventListener("click", () => track("cta_click", { placement: element.dataset.track }));
  });

  const header = document.querySelector("[data-header]");
  const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 18);
  window.addEventListener("scroll", updateHeader, { passive: true });
  updateHeader();

  const menuButton = document.querySelector("[data-menu-button]");
  const mobileMenu = document.querySelector("[data-mobile-menu]");
  const closeMenu = () => {
    if (!menuButton || !mobileMenu) return;
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.querySelector(".sr-only").textContent = "メニューを開く";
    mobileMenu.hidden = true;
    document.body.classList.remove("menu-open");
  };
  menuButton?.addEventListener("click", () => {
    const opening = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(opening));
    menuButton.querySelector(".sr-only").textContent = opening ? "メニューを閉じる" : "メニューを開く";
    mobileMenu.hidden = !opening;
    document.body.classList.toggle("menu-open", opening);
    if (opening) mobileMenu.querySelector("a")?.focus();
  });
  mobileMenu?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  window.addEventListener("resize", () => { if (window.innerWidth > 820) closeMenu(); });

  const dialog = document.querySelector("[data-video-dialog]");
  const video = document.querySelector("[data-demo-video]");
  let videoTrigger = null;
  const closeVideo = () => {
    if (!(dialog instanceof HTMLDialogElement)) return;
    video?.pause();
    dialog.close();
    videoTrigger?.focus();
  };
  document.querySelectorAll("[data-open-video]").forEach((button) => button.addEventListener("click", () => {
    if (!(dialog instanceof HTMLDialogElement)) return;
    videoTrigger = button;
    dialog.showModal();
    dialog.querySelector("[data-close-video]")?.focus();
    track("video_open", { placement: button.dataset.track || "unknown" });
  }));
  document.querySelector("[data-close-video]")?.addEventListener("click", closeVideo);
  dialog?.addEventListener("click", (event) => { if (event.target === dialog) closeVideo(); });
  dialog?.addEventListener("close", () => video?.pause());
  video?.addEventListener("play", () => track("video_play"), { once: true });
  video?.addEventListener("ended", () => track("video_complete"));

  const audienceButtons = [...document.querySelectorAll("[data-audience]")];
  const roleSelect = document.querySelector("[data-role-select]");
  const selectAudience = (audience, { focus = false, emit = true } = {}) => {
    const matched = audienceButtons.find((button) => button.dataset.audience === audience) ?? audienceButtons[0];
    if (!matched) return;
    audienceButtons.forEach((button) => {
      const active = button === matched;
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll("[data-audience-panel]").forEach((panel) => { panel.hidden = panel.dataset.audiencePanel !== matched.dataset.audience; });
    if (roleSelect) roleSelect.value = matched.dataset.audience === "team" ? "school" : matched.dataset.audience;
    if (focus) matched.focus();
    if (emit) track("audience_select", { selected_audience: matched.dataset.audience });
  };
  audienceButtons.forEach((button, index) => {
    button.addEventListener("click", () => selectAudience(button.dataset.audience));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let targetIndex = event.key === "Home" ? 0 : event.key === "End" ? audienceButtons.length - 1 : index + (event.key === "ArrowRight" ? 1 : -1);
      targetIndex = (targetIndex + audienceButtons.length) % audienceButtons.length;
      selectAudience(audienceButtons[targetIndex].dataset.audience, { focus: true });
    });
  });
  const requestedAudience = params.get("audience");
  selectAudience(["home", "farmer", "team"].includes(requestedAudience) ? requestedAudience : "home", { emit: false });

  document.querySelectorAll(".faq-list details").forEach((details) => details.addEventListener("toggle", () => {
    if (details.open) track("faq_open", { question: details.querySelector("summary")?.textContent?.replace("＋", "").trim().slice(0, 150) });
  }));

  const conversionBar = document.querySelector("[data-mobile-conversion]");
  const interest = document.querySelector("#interest");
  if (conversionBar && interest && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => conversionBar.classList.toggle("hidden", entry.isIntersecting), { threshold: .12 }).observe(interest);
  }

  const form = document.querySelector("[data-lead-form]");
  const formStatus = document.querySelector("[data-form-status]");
  const turnstileSlot = document.querySelector("[data-turnstile-slot]");
  const turnstileSiteKey = typeof config.turnstileSiteKey === "string" ? config.turnstileSiteKey.trim() : "";
  let turnstileToken = "";
  let turnstileWidgetId;
  if (turnstileSlot && turnstileSiteKey) {
    turnstileSlot.hidden = false;
    const renderTurnstile = () => {
      if (!window.turnstile || turnstileWidgetId !== undefined) return;
      turnstileSlot.textContent = "";
      turnstileWidgetId = window.turnstile.render(turnstileSlot, {
        sitekey: turnstileSiteKey,
        action: "lead_submit",
        theme: "auto",
        size: "flexible",
        callback: (token) => { turnstileToken = token; },
        "expired-callback": () => { turnstileToken = ""; },
        "error-callback": () => {
          turnstileToken = "";
          setFormStatus("安全確認を読み込めませんでした。ページを再読み込みして、もう一度お試しください。", "error");
        },
      });
    };
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.defer = true;
    script.addEventListener("load", renderTurnstile);
    script.addEventListener("error", () => setFormStatus("安全確認を読み込めませんでした。ページを再読み込みしてください。", "error"));
    document.head.append(script);
  }
  const endpointIsValid = () => {
    if (typeof config.leadEndpoint !== "string" || !config.leadEndpoint.trim()) return false;
    try {
      const url = new URL(config.leadEndpoint, window.location.href);
      return url.protocol === "https:" || url.origin === window.location.origin;
    } catch { return false; }
  };
  const setFormStatus = (message, state = "") => {
    formStatus.textContent = message;
    formStatus.className = `form-status${state ? ` ${state}` : ""}`;
  };
  form?.querySelectorAll("input, select, textarea").forEach((control) => {
    control.addEventListener("input", () => control.classList.remove("invalid"));
    control.addEventListener("change", () => control.classList.remove("invalid"));
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormStatus("");
    const invalid = [...form.elements].filter((control) => typeof control.checkValidity === "function" && !control.checkValidity());
    if (invalid.length > 0) {
      invalid.forEach((control) => control.classList.add("invalid"));
      invalid[0].focus();
      setFormStatus("未入力の必須項目があります。上から順に確認してください。", "error");
      track("lead_validation_error", { invalid_count: invalid.length });
      return;
    }
    if (!endpointIsValid()) {
      setFormStatus("このプレビュー環境は受付先が未設定です。公開前に config.js の leadEndpoint を設定してください。現在は公式サイト・GitHub・Instagramから活動をご確認いただけます。", "error");
      track("lead_endpoint_missing");
      return;
    }
    if (turnstileSiteKey && !turnstileToken) {
      setFormStatus("安全確認が完了していません。確認後にもう一度送信してください。", "error");
      track("lead_turnstile_missing");
      return;
    }

    const submitButton = form.querySelector('button[type="submit"]');
    const originalLabel = submitButton.textContent;
    submitButton.disabled = true;
    submitButton.setAttribute("aria-busy", "true");
    submitButton.textContent = "送信しています";
    const values = Object.fromEntries(new FormData(form).entries());
    const payload = {
      role: values.role,
      scale: values.scale,
      pain: values.pain,
      email: values.email,
      message: values.message || "",
      website: values.website || "",
      consent: values.consent === "on",
      turnstile_token: turnstileToken,
      audience: selectedAudience(),
      attribution,
      submitted_at: new Date().toISOString(),
      source: "inas-demand-validation-lp",
    };
    try {
      const response = await fetch(config.leadEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      form.reset();
      selectAudience("home", { emit: false });
      setFormStatus("ありがとうございます。受付が完了しました。先行案内の準備ができ次第、ご登録のメールアドレスへお知らせします。", "success");
      track("lead_submit_success", { role: payload.role, scale: payload.scale, pain: payload.pain });
    } catch {
      setFormStatus("送信できませんでした。通信状態を確認して、時間をおいてもう一度お試しください。", "error");
      track("lead_submit_error");
    } finally {
      if (turnstileWidgetId !== undefined && window.turnstile) {
        window.turnstile.reset(turnstileWidgetId);
        turnstileToken = "";
      }
      submitButton.disabled = false;
      submitButton.removeAttribute("aria-busy");
      submitButton.textContent = originalLabel;
    }
  });
})();
