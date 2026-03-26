// Live polling for project analysis data
(function() {
  // Find the project id from a data attribute or URL
  var projectId = window.location.pathname.match(/\/projects\/(\d+)/);
  if (!projectId) return;
  projectId = projectId[1];

  // Polling interval in ms
  var POLL_INTERVAL = 3000;

  // The element(s) to update
  var dashboardGrid = document.querySelector('.project-dashboard-grid');
  var reviewCarousel = document.getElementById('project-review');
  var pipelineGrid = document.querySelector('.pipeline-grid');

  function fetchProjectData() {
    fetch(`/api/projects/${projectId}/analysis`)
      .then(function(response) { return response.json(); })
      .then(function(data) {
        // TODO: Update dashboardGrid, reviewCarousel, pipelineGrid with new data
        // For now, just reload the page if data has changed (simple fallback)
        if (window.__lastAnalysisStatus !== data.status) {
          window.__lastAnalysisStatus = data.status;
          window.location.reload();
        }
      })
      .catch(function(err) {
        // Optionally handle errors
      });
  }

  if (dashboardGrid || reviewCarousel || pipelineGrid) {
    setInterval(fetchProjectData, POLL_INTERVAL);
  }
})();
