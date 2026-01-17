/* busu_admin.js */

/* === Highlight active menu item === */
document.addEventListener("DOMContentLoaded", function () {
  const currentUrl = window.location.pathname;
  document.querySelectorAll(".sidebar .nav-link").forEach(link => {
    if (link.getAttribute("href") === currentUrl) {
      link.classList.add("active");
    }
  });
});

/* === Auto-close alerts after 5 seconds === */
document.addEventListener("DOMContentLoaded", function () {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.classList.add("fade");
      setTimeout(() => alert.remove(), 500);
    }, 5000);
  });
});

/* === Dashboard greeting === */
document.addEventListener("DOMContentLoaded", function () {
  const userMenu = document.querySelector(".user-panel .info");
  if (userMenu) {
    const greeting = document.createElement("div");
    const hours = new Date().getHours();
    let message = "Welcome back!";
    if (hours < 12) message = "Good morning!";
    else if (hours < 18) message = "Good afternoon!";
    else message = "Good evening!";
    greeting.textContent = message;
    greeting.style.fontWeight = "600";
    greeting.style.color = "#0f9d58"; // Busu green
    userMenu.appendChild(greeting);
  }
});

/* === Smooth scroll to top button === */
document.addEventListener("DOMContentLoaded", function () {
  const btn = document.createElement("button");
  btn.textContent = "↑ Top";
  btn.className = "btn btn-success";
  btn.style.position = "fixed";
  btn.style.bottom = "20px";
  btn.style.right = "20px";
  btn.style.zIndex = "999";
  btn.style.display = "none";
  document.body.appendChild(btn);

  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  window.addEventListener("scroll", () => {
    if (window.scrollY > 200) {
      btn.style.display = "block";
    } else {
      btn.style.display = "none";
    }
  });
});
