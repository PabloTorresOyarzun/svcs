document.addEventListener("DOMContentLoaded", function () {
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebar = document.getElementById("sidebar");
    const mainContent = document.querySelector(".main-content");

    if (sidebarToggle && sidebar && mainContent) {
        sidebarToggle.addEventListener("click", function (e) {
            e.preventDefault();
            sidebar.classList.toggle("toggled");
            mainContent.classList.toggle("toggled");
        });
    }

    // 2. Scroll to Top Logic
    const btnBackToTop = document.getElementById("btnBackToTop");
    window.onscroll = function () {
        if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
            btnBackToTop.style.display = "block"; // Ahora sí funciona porque no hay un !important bloqueándolo
        } else {
            btnBackToTop.style.display = "none";
        }
    };

    if (btnBackToTop) {
        btnBackToTop.addEventListener("click", function () {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});