document.addEventListener("DOMContentLoaded", function () {
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebar = document.getElementById("sidebar");
    const mainContent = document.querySelector(".c-main");

    if (sidebarToggle && sidebar && mainContent) {
        sidebarToggle.addEventListener("click", function (e) {
            e.preventDefault();
            sidebar.classList.toggle("toggled");
            mainContent.classList.toggle("toggled");
        });
    }

    const btnBackToTop = document.getElementById("btnBackToTop");
    
    if (btnBackToTop) {
        window.addEventListener("scroll", function () {
            if (document.body.scrollTop > 100 || document.documentElement.scrollTop > 100) {
                btnBackToTop.style.display = "flex";
            } else {
                btnBackToTop.style.display = "none";
            }
        });

        btnBackToTop.addEventListener("click", function () {
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    // Intersection Observer para animaciones on-scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: "0px 0px -50px 0px"
    };

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) {
                entry.target.classList.add("a-visible");
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    document.querySelectorAll(".a-observe").forEach(function (el) {
        observer.observe(el);
    });
});