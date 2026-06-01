(function () {
  function setValue(id, value) {
    var node = document.getElementById(id);
    if (!node) return;
    node.value = value;
    node.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function onReady() {
    var button = document.getElementById("dz152fz-reset-banner-colors");
    if (!button) return;
    button.addEventListener("click", function () {
      setValue("id_color_preset", "light");
      setValue("id_custom_bg_color", "#ffffff");
      setValue("id_custom_text_color", "#1f2937");
      setValue("id_custom_primary_color", "#2563eb");
      setValue("id_custom_primary_text_color", "#ffffff");
      setValue("id_custom_border_color", "#d1d5db");
      setValue("id_custom_surface_color", "#f9fafb");
      setValue("id_custom_overlay_color", "#111827");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
