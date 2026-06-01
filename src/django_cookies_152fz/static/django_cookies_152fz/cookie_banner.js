(function () {
  "use strict";

  var RUNTIME_STATE_STORAGE_KEY = "dz152fz:cookie-runtime-state";
  var DEFAULT_EVENT_CONTRACT = {
    version: "1.0",
    namespace: "dz152fz",
    events: {
      runtime_applied: "dz152fz:cookie-runtime:applied",
      runtime_cleanup_applied: "dz152fz:cookie-runtime:cleanup-applied",
      banner_opened: "dz152fz:cookie-banner:opened",
      banner_closed: "dz152fz:cookie-banner:closed",
      banner_custom_opened: "dz152fz:cookie-banner:custom-opened",
      banner_action_submitted: "dz152fz:cookie-banner:action-submitted",
    },
  };

  function hydrateAuditForm(form) {
    if (!form) {
      return;
    }

    var timezone = form.querySelector("[name='client_timezone']");
    if (timezone && window.Intl && Intl.DateTimeFormat) {
      timezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    }

    var languages = form.querySelector("[name='client_languages']");
    if (languages && Array.isArray(navigator.languages)) {
      languages.value = JSON.stringify(navigator.languages);
    }

    var osLocale = form.querySelector("[name='client_os_locale']");
    if (osLocale && navigator.language) {
      osLocale.value = navigator.language;
    }

    var screenWidth = form.querySelector("[name='client_screen_width']");
    var screenHeight = form.querySelector("[name='client_screen_height']");
    if (screenWidth && window.screen) {
      screenWidth.value = window.screen.width || "";
    }
    if (screenHeight && window.screen) {
      screenHeight.value = window.screen.height || "";
    }
  }

  function parseRuntimePayload() {
    var node = document.getElementById("dz152fz-cookie-banner-runtime-data");
    if (!node) {
      return null;
    }

    try {
      return JSON.parse(node.textContent || "{}");
    } catch (error) {
      return null;
    }
  }

  function parseMobileOverridesPayload() {
    var node = document.getElementById("dz152fz-cookie-banner-mobile-overrides");
    if (!node) {
      return null;
    }
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (error) {
      return null;
    }
  }

  function getRuntimeEventContract(payload) {
    var payloadContract =
      payload && typeof payload === "object" ? payload.event_contract : null;
    var payloadEvents =
      payloadContract && typeof payloadContract === "object"
        ? payloadContract.events
        : null;

    return {
      version: String(
        (payloadContract && payloadContract.version) ||
          DEFAULT_EVENT_CONTRACT.version
      ),
      namespace: String(
        (payloadContract && payloadContract.namespace) ||
          DEFAULT_EVENT_CONTRACT.namespace
      ),
      events: {
        runtime_applied: String(
          (payloadEvents && payloadEvents.runtime_applied) ||
            DEFAULT_EVENT_CONTRACT.events.runtime_applied
        ),
        runtime_cleanup_applied: String(
          (payloadEvents && payloadEvents.runtime_cleanup_applied) ||
            DEFAULT_EVENT_CONTRACT.events.runtime_cleanup_applied
        ),
        banner_opened: String(
          (payloadEvents && payloadEvents.banner_opened) ||
            DEFAULT_EVENT_CONTRACT.events.banner_opened
        ),
        banner_closed: String(
          (payloadEvents && payloadEvents.banner_closed) ||
            DEFAULT_EVENT_CONTRACT.events.banner_closed
        ),
        banner_custom_opened: String(
          (payloadEvents && payloadEvents.banner_custom_opened) ||
            DEFAULT_EVENT_CONTRACT.events.banner_custom_opened
        ),
        banner_action_submitted: String(
          (payloadEvents && payloadEvents.banner_action_submitted) ||
            DEFAULT_EVENT_CONTRACT.events.banner_action_submitted
        ),
      },
    };
  }

  function createCustomEvent(name, detail) {
    if (typeof window.CustomEvent === "function") {
      return new CustomEvent(name, { bubbles: true, detail: detail });
    }
    var customEvent = document.createEvent("CustomEvent");
    customEvent.initCustomEvent(name, true, false, detail);
    return customEvent;
  }

  function dispatchRuntimeEvent(target, eventContract, eventKey, detail) {
    // Если проект переопределил имена событий на сервере, используем их.
    var eventName = String(
      (eventContract &&
        eventContract.events &&
        eventContract.events[eventKey]) ||
        (DEFAULT_EVENT_CONTRACT.events[eventKey] || "")
    ).trim();
    if (!eventName) {
      return;
    }

    var payload = {
      contract_version: String(
        (eventContract && eventContract.version) ||
          DEFAULT_EVENT_CONTRACT.version
      ),
      contract_namespace: String(
        (eventContract && eventContract.namespace) ||
          DEFAULT_EVENT_CONTRACT.namespace
      ),
      event_key: String(eventKey || ""),
      event_name: eventName,
      timestamp: new Date().toISOString(),
    };
    if (detail && typeof detail === "object") {
      Object.keys(detail).forEach(function (key) {
        payload[key] = detail[key];
      });
    }

    // Единый CustomEvent-поток для интеграторов (analytics/tag managers/adapters).
    (target || document).dispatchEvent(createCustomEvent(eventName, payload));
  }

  function readStoredRuntimeState() {
    if (!window.localStorage) {
      return null;
    }

    try {
      var rawValue = window.localStorage.getItem(RUNTIME_STATE_STORAGE_KEY);
      if (!rawValue) {
        return null;
      }
      return JSON.parse(rawValue);
    } catch (error) {
      return null;
    }
  }

  function writeStoredRuntimeState(payload) {
    if (!window.localStorage) {
      return;
    }

    try {
      window.localStorage.setItem(
        RUNTIME_STATE_STORAGE_KEY,
        JSON.stringify({
          policyRevisionId: payload.policy_revision_id || null,
          allowedCategories: normalizeCategoryList(payload.allowed_categories),
        })
      );
    } catch (error) {
      return;
    }
  }

  function normalizeCategoryList(values) {
    if (!Array.isArray(values)) {
      return [];
    }

    var normalized = [];
    values.forEach(function (value) {
      var categoryCode = String(value || "").trim();
      if (categoryCode && normalized.indexOf(categoryCode) === -1) {
        normalized.push(categoryCode);
      }
    });
    return normalized;
  }

  function getRemovedCategories(previousState, payload) {
    var previousCategories = normalizeCategoryList(
      previousState && previousState.allowedCategories
    );
    var nextCategories = normalizeCategoryList(payload.allowed_categories);

    return previousCategories.filter(function (categoryCode) {
      return nextCategories.indexOf(categoryCode) === -1;
    });
  }

  function getCleanupItems(payload, removedCategories) {
    if (!Array.isArray(payload.cleanup_items) || !removedCategories.length) {
      return [];
    }

    return payload.cleanup_items.filter(function (item) {
      return removedCategories.indexOf(String(item.category_code || "")) !== -1;
    });
  }

  function collectRegistryCodes(items) {
    if (!Array.isArray(items)) {
      return [];
    }

    var codes = [];
    items.forEach(function (item) {
      var code = String(item.code || "").trim();
      if (code && codes.indexOf(code) === -1) {
        codes.push(code);
      }
    });
    return codes;
  }

  function getAllowedScriptItems(payload) {
    var allowedCategories = normalizeCategoryList(payload.allowed_categories);
    if (
      !payload.consent_allows_runtime ||
      !Array.isArray(payload.script_items) ||
      !allowedCategories.length
    ) {
      return [];
    }

    return payload.script_items.filter(function (item) {
      return (
        allowedCategories.indexOf(String(item.category_code || "")) !== -1 &&
        String(item.src_url || "").trim()
      );
    });
  }

  function findManagedScript(code) {
    var scripts = document.querySelectorAll("script[data-cookie-runtime-code]");
    for (var index = 0; index < scripts.length; index += 1) {
      if (scripts[index].getAttribute("data-cookie-runtime-code") === code) {
        return scripts[index];
      }
    }
    return null;
  }

  function injectManagedScript(item) {
    var code = String(item.code || "").trim();
    var srcUrl = String(item.src_url || "").trim();
    if (!code || !srcUrl || findManagedScript(code)) {
      return;
    }

    var script = document.createElement("script");
    script.src = srcUrl;
    script.defer = true;
    script.async = false;
    script.setAttribute("data-cookie-runtime-code", code);
    script.setAttribute(
      "data-cookie-runtime-category",
      String(item.category_code || "")
    );
    document.head.appendChild(script);
  }

  function removeManagedScriptsByCategories(categoryCodes) {
    if (!categoryCodes.length) {
      return;
    }

    var scripts = document.querySelectorAll("script[data-cookie-runtime-category]");
    scripts.forEach(function (script) {
      if (
        categoryCodes.indexOf(
          script.getAttribute("data-cookie-runtime-category") || ""
        ) !== -1
      ) {
        script.remove();
      }
    });
  }

  function buildCookieDeletionPaths() {
    var pathname = window.location.pathname || "/";
    var parts = pathname.split("/");
    var paths = ["/"];
    var currentPath = "";

    for (var index = 1; index < parts.length; index += 1) {
      if (!parts[index]) {
        continue;
      }
      currentPath += "/" + parts[index];
      if (paths.indexOf(currentPath) === -1) {
        paths.unshift(currentPath);
      }
    }

    return paths;
  }

  function buildCookieDeletionDomains() {
    var hostname = String(window.location.hostname || "").trim();
    if (!hostname || hostname === "localhost" || hostname.indexOf(".") === -1) {
      return [""];
    }

    var domains = ["", hostname, "." + hostname];
    var parts = hostname.split(".");
    for (var index = 1; index < parts.length - 1; index += 1) {
      var domain = parts.slice(index).join(".");
      if (domains.indexOf(domain) === -1) {
        domains.push(domain);
      }
      if (domains.indexOf("." + domain) === -1) {
        domains.push("." + domain);
      }
    }

    return domains;
  }

  function deleteCookie(name) {
    var normalizedName = String(name || "").trim();
    if (!normalizedName) {
      return;
    }

    var expires = "Thu, 01 Jan 1970 00:00:00 GMT";
    var paths = buildCookieDeletionPaths();
    var domains = buildCookieDeletionDomains();

    paths.forEach(function (path) {
      domains.forEach(function (domain) {
        var cookieValue =
          normalizedName +
          "=; expires=" +
          expires +
          "; Max-Age=0; path=" +
          path +
          "; SameSite=Lax";
        if (domain) {
          cookieValue += "; domain=" + domain;
        }
        document.cookie = cookieValue;
      });
    });
  }

  function cleanupRegistryItem(item) {
    if (!item) {
      return;
    }

    var cookieNames = Array.isArray(item.cookie_names) ? item.cookie_names : [];
    cookieNames.forEach(deleteCookie);
  }

  function applyRuntimeCleanup(previousState, payload) {
    var removedCategories = getRemovedCategories(previousState, payload);
    if (!removedCategories.length) {
      return {
        removed_categories: [],
        cleanup_item_codes: [],
      };
    }

    // Удаляем только то, что было отключено относительно предыдущего состояния.
    var cleanupItems = getCleanupItems(payload, removedCategories);
    removeManagedScriptsByCategories(removedCategories);
    cleanupItems.forEach(cleanupRegistryItem);
    return {
      removed_categories: removedCategories,
      cleanup_item_codes: collectRegistryCodes(cleanupItems),
    };
  }

  function applyCookieRuntime(payload, eventContract) {
    var runtimePayload =
      payload && typeof payload === "object" ? payload : {};
    if (!runtimePayload.enabled) {
      dispatchRuntimeEvent(
        document,
        eventContract,
        "runtime_applied",
        {
          runtime_enabled: false,
          policy_revision_id: runtimePayload.policy_revision_id || null,
          policy_revision_version: runtimePayload.policy_revision_version || null,
          consent_status: runtimePayload.status || null,
          consent_allows_runtime: false,
          selected_categories: [],
          allowed_categories: [],
          loaded_script_codes: [],
        }
      );
      return;
    }

    var previousState = readStoredRuntimeState();
    var cleanupResult = applyRuntimeCleanup(previousState, runtimePayload);
    if (
      cleanupResult.removed_categories.length ||
      cleanupResult.cleanup_item_codes.length
    ) {
      dispatchRuntimeEvent(
        document,
        eventContract,
        "runtime_cleanup_applied",
        {
          policy_revision_id: runtimePayload.policy_revision_id || null,
          removed_categories: cleanupResult.removed_categories,
          cleanup_item_codes: cleanupResult.cleanup_item_codes,
        }
      );
    }

    var scriptItems = getAllowedScriptItems(runtimePayload);
    scriptItems.forEach(injectManagedScript);
    writeStoredRuntimeState(runtimePayload);
    dispatchRuntimeEvent(
      document,
      eventContract,
      "runtime_applied",
      {
        runtime_enabled: true,
        policy_revision_id: runtimePayload.policy_revision_id || null,
        policy_revision_version: runtimePayload.policy_revision_version || null,
        consent_status: runtimePayload.status || null,
        consent_allows_runtime: !!runtimePayload.consent_allows_runtime,
        selected_categories: normalizeCategoryList(
          runtimePayload.selected_categories
        ),
        allowed_categories: normalizeCategoryList(runtimePayload.allowed_categories),
        loaded_script_codes: collectRegistryCodes(scriptItems),
      }
    );
  }

  function collectSelectedOptionalCategories(form) {
    if (!form) {
      return [];
    }
    var selectedCategories = [];
    form
      .querySelectorAll("input[name='selected_categories']")
      .forEach(function (checkbox) {
        if (checkbox.checked) {
          var code = String(checkbox.value || "").trim();
          if (code && selectedCategories.indexOf(code) === -1) {
            selectedCategories.push(code);
          }
        }
      });
    return selectedCategories;
  }

  function resolveBannerAction(event, form) {
    var submitter = event.submitter || document.activeElement;
    if (
      submitter &&
      submitter.name === "banner_action" &&
      String(submitter.value || "").trim()
    ) {
      return String(submitter.value || "").trim();
    }

    var hiddenAction = form.querySelector("input[name='banner_action']");
    if (hiddenAction && String(hiddenAction.value || "").trim()) {
      return String(hiddenAction.value || "").trim();
    }
    return "";
  }

  function collectChoiceCheckboxes(root) {
    if (!root) {
      return [];
    }
    return Array.prototype.slice.call(
      root.querySelectorAll("input[name='selected_categories']")
    );
  }

  function buildChoiceStateLabel(root, state) {
    if (!root) {
      return "";
    }
    if (state === "accept_all") {
      return String(root.getAttribute("data-cookie-choice-all-label") || "");
    }
    if (state === "required_only") {
      return String(root.getAttribute("data-cookie-choice-required-label") || "");
    }
    if (state === "reject_all") {
      return String(root.getAttribute("data-cookie-choice-reject-label") || "");
    }
    return String(root.getAttribute("data-cookie-choice-custom-label") || "");
  }

  function detectChoiceStateFromCheckboxes(checkboxes) {
    if (!checkboxes.length) {
      return "required_only";
    }
    var checkedCount = checkboxes.filter(function (checkbox) {
      return !!checkbox.checked;
    }).length;
    if (checkedCount <= 0) {
      return "required_only";
    }
    if (checkedCount >= checkboxes.length) {
      return "accept_all";
    }
    return "custom";
  }

  function setupCookieChoiceState(root) {
    if (!root) {
      return;
    }

    var checkboxes = collectChoiceCheckboxes(root);
    var indicator = root.querySelector("[data-cookie-choice-indicator]");
    var screenReaderStatus = root.querySelector("[data-cookie-choice-status]");
    var actionButtons = root.querySelectorAll("[data-cookie-choice-action]");
    var initialState = String(
      root.getAttribute("data-cookie-choice-initial-state") || ""
    ).trim();

    function updateChoiceState(nextState) {
      var state = String(nextState || "custom");
      var label = buildChoiceStateLabel(root, state);
      root.setAttribute("data-cookie-choice-state", state);

      actionButtons.forEach(function (button) {
        var isActive =
          String(button.getAttribute("data-cookie-choice-action") || "") === state;
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
        button.classList.toggle("dz152fz-cookie-choice-action--active", isActive);
      });

      if (indicator) {
        indicator.textContent = label;
      }
      if (screenReaderStatus) {
        screenReaderStatus.textContent = label;
      }
    }

    function setAllOptionalCategories(checked) {
      checkboxes.forEach(function (checkbox) {
        checkbox.checked = !!checked;
      });
    }

    function hasActionButton(state) {
      var normalizedState = String(state || "").trim();
      if (!normalizedState) {
        return false;
      }
      for (var index = 0; index < actionButtons.length; index += 1) {
        if (
          String(
            actionButtons[index].getAttribute("data-cookie-choice-action") || ""
          ) === normalizedState
        ) {
          return true;
        }
      }
      return false;
    }

    actionButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        var action = String(
          button.getAttribute("data-cookie-choice-action") || ""
        ).trim();
        if (action === "accept_all") {
          setAllOptionalCategories(true);
          updateChoiceState("accept_all");
          return;
        }
        if (action === "required_only") {
          setAllOptionalCategories(false);
          updateChoiceState("required_only");
          return;
        }
        if (action === "reject_all") {
          setAllOptionalCategories(false);
          updateChoiceState("reject_all");
          return;
        }
        if (action === "custom") {
          updateChoiceState("custom");
        }
      });
    });

    checkboxes.forEach(function (checkbox) {
      checkbox.addEventListener("change", function () {
        updateChoiceState(detectChoiceStateFromCheckboxes(checkboxes));
      });
    });

    if (hasActionButton(initialState)) {
      updateChoiceState(initialState);
      return;
    }
    updateChoiceState(detectChoiceStateFromCheckboxes(checkboxes));
  }

  function setupCookieBanner(root, eventContract, runtimePayload) {
    if (!root) {
      return;
    }

    root.classList.add("dz152fz-cookie-banner--interactive");
    var panel = root.querySelector("[data-cookie-banner-panel]");
    var launcher = root.querySelector("[data-cookie-banner-launcher]");
    var form = root.querySelector("[data-cookie-banner-form]");
    var customToggle = root.querySelector("[data-cookie-banner-open-custom]");
    var customDetails = root.querySelector("[data-cookie-banner-custom]");
    var backdrop = root.querySelector("[data-cookie-banner-backdrop]");
    var dismissControl = root.querySelector("[data-cookie-banner-dismiss]");
    var rejectControl = root.querySelector(
      "[data-cookie-choice-action='reject_all']"
    );
    var mobileOverrides = parseMobileOverridesPayload();
    var lastTrigger = null;
    var blockingModeEnabledDesktop =
      String(root.getAttribute("data-cookie-banner-blocking-mode") || "") ===
      "true";
    // Блокировка зависит от вьюпорта (на мобильном может действовать
    // mobile-override). "Gate" — есть ли вообще основание блокировать
    // (баннер показывается и осмысленный выбор ещё не сделан) — одинаков
    // для desktop и mobile и приходит отдельным серверным атрибутом.
    var blockingGateOpen =
      String(root.getAttribute("data-cookie-banner-blocking-gate") || "") ===
      "true";
    var isBlockingModeEnabled = blockingModeEnabledDesktop;
    var isBlockingModeActive = blockingGateOpen;
    var isInitialVisit =
      String(root.getAttribute("data-cookie-banner-initial-visit") || "") ===
      "true";
    var isReopenAfterSavedChoice =
      String(
        root.getAttribute("data-cookie-banner-reopen-after-saved-choice") || ""
      ) === "true";

    function isBlockingActive() {
      return !!(isBlockingModeEnabled && isBlockingModeActive);
    }

    function getVariantContext() {
      return {
        banner_variant: String(
          root.getAttribute("data-cookie-banner-variant") || ""
        ),
        consent_ui_variant: String(
          root.getAttribute("data-cookie-banner-consent-ui") || ""
        ),
        reconsent_notice_variant: String(
          root.getAttribute("data-cookie-banner-reconsent-variant") || ""
        ),
      };
    }

    function syncReconsentNoticeVariant(variantCode) {
      root
        .querySelectorAll("[data-cookie-banner-reconsent-notice]")
        .forEach(function (notice) {
          notice.classList.remove("dz152fz-cookie-banner__notice--inline");
          notice.classList.remove("dz152fz-cookie-banner__notice--alert");
          notice.classList.add(
            "dz152fz-cookie-banner__notice--" + String(variantCode || "inline")
          );
        });
    }

    function applyTextOverrides(textValues) {
      if (!textValues || typeof textValues !== "object") {
        return;
      }
      root
        .querySelectorAll("[data-cookie-banner-text-key]")
        .forEach(function (node) {
          var key = String(node.getAttribute("data-cookie-banner-text-key") || "");
          if (!key || typeof textValues[key] === "undefined") {
            return;
          }
          node.textContent = String(textValues[key] || "");
        });
      if (typeof textValues.accept_all_label === "string") {
        root.setAttribute(
          "data-cookie-choice-all-label",
          String(textValues.accept_all_label)
        );
      }
      if (typeof textValues.required_only_label === "string") {
        root.setAttribute(
          "data-cookie-choice-required-label",
          String(textValues.required_only_label)
        );
      }
      if (typeof textValues.reject_label === "string") {
        root.setAttribute(
          "data-cookie-choice-reject-label",
          String(textValues.reject_label)
        );
      }
      if (typeof textValues.custom_section_summary === "string") {
        root.setAttribute(
          "data-cookie-choice-custom-label",
          String(textValues.custom_section_summary)
        );
      }
    }

    function applyResponsiveOverrides() {
      if (!window.matchMedia) {
        return;
      }
      var isMobileViewport = window.matchMedia("(max-width: 900px)").matches;
      var desktopVariant = String(
        root.getAttribute("data-cookie-banner-variant-desktop") ||
          root.getAttribute("data-cookie-banner-variant") ||
          ""
      );
      var desktopConsentUi = String(
        root.getAttribute("data-cookie-banner-consent-ui-desktop") ||
          root.getAttribute("data-cookie-banner-consent-ui") ||
          ""
      );
      var desktopReconsentVariant = String(
        root.getAttribute("data-cookie-banner-reconsent-variant-desktop") ||
          root.getAttribute("data-cookie-banner-reconsent-variant") ||
          ""
      );
      if (!root.hasAttribute("data-cookie-banner-variant-desktop")) {
        root.setAttribute("data-cookie-banner-variant-desktop", desktopVariant);
      }
      if (!root.hasAttribute("data-cookie-banner-consent-ui-desktop")) {
        root.setAttribute(
          "data-cookie-banner-consent-ui-desktop",
          desktopConsentUi
        );
      }
      if (!root.hasAttribute("data-cookie-banner-reconsent-variant-desktop")) {
        root.setAttribute(
          "data-cookie-banner-reconsent-variant-desktop",
          desktopReconsentVariant
        );
      }

      var effectiveVariant = desktopVariant;
      var effectiveConsentUi = desktopConsentUi;
      var effectiveReconsentVariant = desktopReconsentVariant;
      var effectiveClosePlacement = String(
        root.getAttribute("data-cookie-banner-close-placement") || "right"
      );
      var effectiveShowCloseControl =
        String(root.getAttribute("data-cookie-banner-show-close-control") || "") ===
        "true";
      var effectiveShowRejectAction =
        !rejectControl || !rejectControl.hasAttribute("hidden");
      var effectiveTextValues = null;

      if (isMobileViewport && mobileOverrides && typeof mobileOverrides === "object") {
        effectiveVariant = String(mobileOverrides.banner_variant || desktopVariant);
        effectiveConsentUi = String(
          mobileOverrides.consent_ui_variant || desktopConsentUi
        );
        effectiveReconsentVariant = String(
          mobileOverrides.reconsent_notice_variant || desktopReconsentVariant
        );
        effectiveClosePlacement = String(
          mobileOverrides.close_control_placement || effectiveClosePlacement
        );
        if (typeof mobileOverrides.show_close_control === "boolean") {
          effectiveShowCloseControl = mobileOverrides.show_close_control;
        }
        if (typeof mobileOverrides.show_reject_action === "boolean") {
          effectiveShowRejectAction = mobileOverrides.show_reject_action;
        }
        effectiveTextValues = mobileOverrides.text_values || null;
      }

      root.setAttribute("data-cookie-banner-variant", effectiveVariant);
      root.setAttribute("data-cookie-banner-consent-ui", effectiveConsentUi);
      root.setAttribute(
        "data-cookie-banner-reconsent-variant",
        effectiveReconsentVariant
      );
      root.setAttribute("data-cookie-banner-close-placement", effectiveClosePlacement);
      syncReconsentNoticeVariant(effectiveReconsentVariant);
      if (dismissControl) {
        dismissControl.hidden = !effectiveShowCloseControl;
      }
      if (rejectControl) {
        rejectControl.hidden = !effectiveShowRejectAction;
      }
      if (effectiveTextValues) {
        applyTextOverrides(effectiveTextValues);
      }
      // Эффективное включение блокировки для текущего вьюпорта: на мобильном
      // используем mobile-override, на десктопе — серверное desktop-значение.
      var effectiveBlockingEnabled = blockingModeEnabledDesktop;
      if (
        isMobileViewport &&
        mobileOverrides &&
        typeof mobileOverrides.blocking_mode_until_choice === "boolean"
      ) {
        effectiveBlockingEnabled = mobileOverrides.blocking_mode_until_choice;
      }
      isBlockingModeEnabled = effectiveBlockingEnabled;
      updateLauncherState();
    }

    function isModalVariant() {
      return getVariantContext().banner_variant === "modal" || isBlockingActive();
    }

    function syncModalState() {
      var isModalOpen = !!(panel && !panel.hidden && isModalVariant());
      if (backdrop) {
        backdrop.hidden = !isModalOpen;
      }
      if (panel) {
        panel.setAttribute("aria-modal", isModalVariant() ? "true" : "false");
      }
      root.classList.toggle(
        "dz152fz-cookie-banner--blocking-active",
        !!(panel && !panel.hidden && isBlockingActive())
      );
      if (document.body && document.body.classList) {
        document.body.classList.toggle(
          "dz152fz-cookie-banner-modal-open",
          isModalOpen
        );
        document.body.classList.toggle(
          "dz152fz-cookie-banner-blocking-open",
          !!(panel && !panel.hidden && isBlockingActive())
        );
      }
    }

    function updateLauncherState() {
      if (launcher) {
        launcher.setAttribute(
          "aria-expanded",
          panel && !panel.hidden ? "true" : "false"
        );
      }
      if (customToggle && customDetails) {
        customToggle.setAttribute(
          "aria-expanded",
          customDetails.open ? "true" : "false"
        );
      }
      syncModalState();
    }

    function openBanner(trigger, reason) {
      if (!panel) {
        return;
      }
      lastTrigger = trigger || launcher || null;
      panel.hidden = false;
      root.setAttribute("data-cookie-banner-open", "true");
      updateLauncherState();
      var openVariantContext = getVariantContext();
      dispatchRuntimeEvent(root, eventContract, "banner_opened", {
        reason: String(reason || ""),
        panel_open: true,
        initial_visit: isInitialVisit,
        reopen_after_saved_choice: isReopenAfterSavedChoice,
        banner_state: String(root.getAttribute("data-cookie-banner-state") || ""),
        preview_mode:
          String(root.getAttribute("data-cookie-banner-preview-mode") || "") ===
          "true",
        policy_revision_id:
          runtimePayload && runtimePayload.policy_revision_id
            ? runtimePayload.policy_revision_id
            : null,
        contract_version: String(
          root.getAttribute("data-cookie-banner-contract-version") || ""
        ),
        banner_variant: openVariantContext.banner_variant,
        consent_ui_variant: openVariantContext.consent_ui_variant,
        reconsent_notice_variant: openVariantContext.reconsent_notice_variant,
      });
      var autofocusTarget =
        panel.querySelector("button[type='submit'], [href], input, summary") ||
        panel.querySelector("button, [href], input, summary");
      if (autofocusTarget) {
        autofocusTarget.focus();
      }
    }

    function closeBanner(reason) {
      if (!panel) {
        return;
      }
      if (isBlockingActive()) {
        return;
      }
      panel.hidden = true;
      root.setAttribute("data-cookie-banner-open", "false");
      updateLauncherState();
      var closeVariantContext = getVariantContext();
      dispatchRuntimeEvent(root, eventContract, "banner_closed", {
        reason: String(reason || ""),
        panel_open: false,
        banner_state: String(root.getAttribute("data-cookie-banner-state") || ""),
        banner_variant: closeVariantContext.banner_variant,
        consent_ui_variant: closeVariantContext.consent_ui_variant,
        reconsent_notice_variant: closeVariantContext.reconsent_notice_variant,
      });
      if (lastTrigger && typeof lastTrigger.focus === "function") {
        lastTrigger.focus();
      }
    }

    if (launcher && panel) {
      launcher.addEventListener("click", function (event) {
        if (panel.hidden) {
          event.preventDefault();
          openBanner(launcher, "launcher_click");
        }
      });
    }

    if (customToggle && customDetails) {
      customToggle.addEventListener("click", function () {
        customDetails.open = true;
        updateLauncherState();
        var customVariantContext = getVariantContext();
        dispatchRuntimeEvent(root, eventContract, "banner_custom_opened", {
          panel_open: !!(panel && !panel.hidden),
          custom_open: true,
          banner_state: String(root.getAttribute("data-cookie-banner-state") || ""),
          banner_variant: customVariantContext.banner_variant,
          consent_ui_variant: customVariantContext.consent_ui_variant,
          reconsent_notice_variant: customVariantContext.reconsent_notice_variant,
        });
        var firstCheckbox = customDetails.querySelector("input[type='checkbox']");
        if (firstCheckbox) {
          firstCheckbox.focus();
        }
      });

      customDetails.addEventListener("toggle", function () {
        updateLauncherState();
      });
    }

    if (backdrop) {
      backdrop.addEventListener("click", function () {
        if (isBlockingActive()) {
          return;
        }
        if (panel && !panel.hidden) {
          closeBanner("backdrop_click");
        }
      });
    }

    if (form) {
      form.addEventListener("submit", function (event) {
        // Логируем пользовательское действие до перехода/POST редиректа.
        dispatchRuntimeEvent(root, eventContract, "banner_action_submitted", {
          action: resolveBannerAction(event, form),
          selected_optional_categories: collectSelectedOptionalCategories(form),
          panel_open: !!(panel && !panel.hidden),
          banner_state: String(root.getAttribute("data-cookie-banner-state") || ""),
          policy_revision_id:
            runtimePayload && runtimePayload.policy_revision_id
              ? runtimePayload.policy_revision_id
              : null,
          banner_variant: getVariantContext().banner_variant,
          consent_ui_variant: getVariantContext().consent_ui_variant,
          reconsent_notice_variant: getVariantContext().reconsent_notice_variant,
        });
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && panel && !panel.hidden) {
        if (isBlockingActive()) {
          event.preventDefault();
          return;
        }
        closeBanner("escape_key");
        return;
      }
      if (event.key !== "Tab" || !panel || panel.hidden || !isModalVariant()) {
        return;
      }
      var focusableElements = panel.querySelectorAll(
        "a[href], button:not([disabled]), input:not([disabled]), summary, [tabindex]:not([tabindex='-1'])"
      );
      if (!focusableElements.length) {
        return;
      }
      var firstElement = focusableElements[0];
      var lastElement = focusableElements[focusableElements.length - 1];
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    });

    updateLauncherState();
    applyResponsiveOverrides();
    if (window.matchMedia) {
      var mobileMql = window.matchMedia("(max-width: 900px)");
      if (typeof mobileMql.addEventListener === "function") {
        mobileMql.addEventListener("change", applyResponsiveOverrides);
      } else if (typeof mobileMql.addListener === "function") {
        mobileMql.addListener(applyResponsiveOverrides);
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var runtimePayload = parseRuntimePayload();
    var eventContract = getRuntimeEventContract(runtimePayload);

    document.querySelectorAll("[data-cookie-audit-form]").forEach(hydrateAuditForm);
    applyCookieRuntime(runtimePayload, eventContract);
    document
      .querySelectorAll("[data-cookie-choice-root]")
      .forEach(setupCookieChoiceState);
    document.querySelectorAll("[data-cookie-banner-root]").forEach(function (root) {
      setupCookieBanner(root, eventContract, runtimePayload);
    });
  });
})();
