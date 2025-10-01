let characterChart = null;
let locationChart = null;
let currentAnalysisData = null; // To store analysis results temporarily

// --- Script Analysis Logic ---
async function analyzeScript(projectId) {
    const scriptText = document.getElementById('script-text').value;
    const resultsContainer = document.getElementById('script-analysis-results');
    const saveProjectContainer = document.getElementById('save-project-container');

    if (!scriptText.trim()) {
        resultsContainer.innerHTML = '<p class="error">Script text cannot be empty.</p>';
        return;
    }

    resultsContainer.innerHTML = '<p>Analyzing, please wait...</p>';
    saveProjectContainer.style.display = 'none'; // Hide save button during analysis

    try {
        const response = await fetch('/api/script/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_id: projectId, script: scriptText})
        });
        const data = await response.json();
        displayAnalysisResults(data, projectId, scriptText);
    } catch (error) {
        resultsContainer.innerHTML = '<p class="error">Failed to reach API.</p>';
        console.error("Error analyzing script:", error);
    }
}

function displayAnalysisResults(data, projectId, scriptText) {
    const resultsContainer = document.getElementById('script-analysis-results');
    const chartSection = document.getElementById('chart-section');
    const saveProjectContainer = document.getElementById('save-project-container');
    resultsContainer.innerHTML = ''; // Clear previous results
    chartSection.style.display = 'none';
    saveProjectContainer.style.display = 'none';

    if (data.error) {
        resultsContainer.innerHTML = `<p class="error">${data.error}</p>`;
        if (data.raw_response_for_debugging) {
            resultsContainer.innerHTML += `<h4>Raw AI Response:</h4><pre>${data.raw_response_for_debugging}</pre>`;
        }
        return;
    }

    currentAnalysisData = data; // Store analysis data
    currentAnalysisData.script_text = scriptText; // Store script text too

    let html = '<h4>Characters</h4><ul>';
    data.characters.forEach(char => {
        html += `<li><strong>${char.name}</strong> (${char.dialogue_lines} lines)</li>`;
    });
    html += '</ul>';

    html += '<h4>Locations</h4><ul>';
    data.locations.forEach(loc => {
        html += `<li><strong>${loc.name}</strong> (${loc.scenes} scenes)</li>`;
    });
    html += '</ul>';

    html += '<h4>Props</h4><ul>';
    data.props.forEach(prop => {
        html += `<li>${prop}</li>`;
    });
    html += '</ul>';

    html += `<h4>Estimated Scenes: ${data.estimated_scenes}</h4>`;

    resultsContainer.innerHTML = html;
    chartSection.style.display = 'block'; // Show the charts

    createCharacterChart(data.characters);
    createLocationChart(data.locations);

    if (!projectId) { // Only show save button if it's a new script analysis
        saveProjectContainer.style.display = 'block';
    }
}

function createCharacterChart(characters) {
    const ctx = document.getElementById('character-chart').getContext('2d');
    if (characterChart) {
        characterChart.destroy();
    }
    characterChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: characters.map(c => c.name),
            datasets: [{
                label: '# of Dialogue Lines',
                data: characters.map(c => c.dialogue_lines),
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgba(75, 192, 192, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function createLocationChart(locations) {
    const ctx = document.getElementById('location-chart').getContext('2d');
    if (locationChart) {
        locationChart.destroy();
    }
    locationChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: locations.map(l => l.name),
            datasets: [{
                label: '# of Scenes',
                data: locations.map(l => l.scenes),
                backgroundColor: [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 206, 86, 0.2)',
                    'rgba(75, 192, 192, 0.2)',
                    'rgba(153, 102, 255, 0.2)',
                    'rgba(255, 159, 64, 0.2)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)'
                ],
                borderWidth: 1
            }]
        }
    });
}

async function saveAnalysisAsProject() {
    if (!currentAnalysisData || !currentAnalysisData.script_text) {
        alert("No analysis data to save. Please analyze a script first.");
        return;
    }

    const projectName = prompt("Enter a name for your new project:");
    if (!projectName) {
        alert("Project name cannot be empty.");
        return;
    }

    try {
        const response = await fetch('/projects/new', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name: projectName,
                script_text: currentAnalysisData.script_text,
                analysis_json: JSON.stringify(currentAnalysisData) // Pass analysis data to be saved
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Failed to save project.");
        }

        const newProject = await response.json();
        alert("Project saved successfully!");
        window.location.href = `/projects/${newProject.id}`;

    } catch (error) {
        alert(`Error saving project: ${error.message}`);
        console.error("Error saving project:", error);
    }
}

// This function is now only called from project_detail.html
async function generateBudget(projectId) {
    if (!projectId) {
        alert("Project ID is required to generate budget.");
        return;
    }

    const generateButton = document.querySelector('button[onclick="generateBudget(' + projectId + ')"]');
    generateButton.textContent = 'Generating...';
    generateButton.disabled = true;

    try {
        const response = await fetch('/api/budget/generate_from_script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Failed to generate budget.");
        }

        // Redirect to the budget page
        window.location.href = `/budget_oversight/${projectId}`;

    } catch (error) {
        alert(`Error generating budget: ${error.message}`);
        console.error("Error generating budget:", error);
        generateButton.textContent = 'Generate Budget from Analysis';
        generateButton.disabled = false;
    }
}