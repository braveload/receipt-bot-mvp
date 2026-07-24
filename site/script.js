const header = document.querySelector("[data-header]");
const menuButton = document.querySelector(".menu-button");
const nav = document.querySelector("#main-nav");

const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 24);
updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

menuButton?.addEventListener("click", () => {
  const open = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!open));
  nav?.classList.toggle("open", !open);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav?.classList.contains("open")) {
    nav.classList.remove("open");
    menuButton?.setAttribute("aria-expanded", "false");
    menuButton?.focus();
  }
});

document.addEventListener("click", (event) => {
  if (!nav?.classList.contains("open")) return;
  if (nav.contains(event.target) || menuButton?.contains(event.target)) return;
  nav.classList.remove("open");
  menuButton?.setAttribute("aria-expanded", "false");
});

nav?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    menuButton?.setAttribute("aria-expanded", "false");
    nav.classList.remove("open");
  });
});

const revealItems = document.querySelectorAll(".reveal");
if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add("visible"));
}

document.querySelector("[data-contact-form]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const status = formElement.querySelector("[data-form-status]");
  const button = formElement.querySelector('button[type="submit"]');
  if (!formElement.reportValidity()) return;

  const form = new FormData(formElement);
  const payload = {
    name: String(form.get("name") || "").trim(),
    contact: String(form.get("contact") || "").trim(),
    message: String(form.get("message") || "").trim(),
    privacy_consent: form.get("privacy_consent") === "on",
    website: String(form.get("website") || ""),
  };

  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  status.className = "form-status";
  status.textContent = "문의를 안전하게 접수하고 있습니다…";

  try {
    const response = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(response.status === 429 ? "잠시 후 다시 문의해 주세요." : "접수에 실패했습니다.");
    }
    status.className = "form-status success";
    status.textContent = `접수되었습니다. 접수번호: ${result.reference}`;
    formElement.reset();
  } catch (error) {
    status.className = "form-status error";
    status.textContent = `${error.message} 아래 이메일로 직접 문의해 주세요.`;
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
});
