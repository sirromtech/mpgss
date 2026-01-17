document.addEventListener('DOMContentLoaded', function () {
  const toggleBtn = document.getElementById('toggleSidebarBtn');
  const toggleIcon = document.getElementById('toggleIcon');
  const toggleText = document.getElementById('toggleText');
  const sidebar = document.getElementById('sidebarMenu');

  sidebar.addEventListener('hidden.bs.collapse', function () {
    toggleIcon.classList.remove('bi-chevron-double-left');
    toggleIcon.classList.add('bi-chevron-double-right');
    toggleText.textContent = 'Expand Sidebar';
  });

  sidebar.addEventListener('shown.bs.collapse', function () {
    toggleIcon.classList.remove('bi-chevron-double-right');
    toggleIcon.classList.add('bi-chevron-double-left');
    toggleText.textContent = 'Collapse Sidebar';
  });
});

   // Show popup when page loads
  
  window.onload = function () {
    document.getElementById('popup').style.display = 'block';
    document.getElementById('overlay').style.display = 'block';
  };

  function closePopup() {
    document.getElementById('popup').style.display = 'none';
    document.getElementById('overlay').style.display = 'none';
  }

