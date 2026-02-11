// Needle - Java Thread Dump Analyzer - Frontend Application

document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const newUploadBtn = document.getElementById('new-upload-btn');

    // File upload handlers
    browseBtn.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('click', (e) => {
        if (e.target === dropZone || e.target.classList.contains('upload-icon')) {
            fileInput.click();
        }
    });

    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop handlers
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);

    // New upload button
    newUploadBtn.addEventListener('click', resetUpload);

    // Initialize navigation
    initializeNavigation();

    // Store current filename(s)
    window.currentFileNames = [];
}

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('drop-zone').classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('drop-zone').classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('drop-zone').classList.remove('drag-over');

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
        window.currentFileNames = files.map(f => f.name);
        uploadFiles(files);
    }
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
        window.currentFileNames = files.map(f => f.name);
        uploadFiles(files);
    }
}

async function uploadFiles(files) {
    // Validate files
    const validExtensions = ['.log', '.txt'];
    
    for (const file of files) {
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!validExtensions.includes(fileExtension)) {
            showError(`Invalid file format for '${file.name}'. Please upload .log or .txt files.`);
            return;
        }
        
        // Check file size (100MB)
        const maxSize = 100 * 1024 * 1024;
        if (file.size > maxSize) {
            showError(`File '${file.name}' too large. Maximum size is 100MB.`);
            return;
        }
    }

    // Show loading
    showLoading();

    // Create form data with all files
    const formData = new FormData();
    for (const file of files) {
        formData.append('files', file);
    }

    try {
        // Upload and analyze
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to analyze thread dump(s)');
        }

        const data = await response.json();
        displayResults(data);

    } catch (error) {
        showError(error.message || 'Failed to upload files. Please try again.');
        hideLoading();
    }
}

function showLoading() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('upload-section').classList.add('hidden');
    document.getElementById('error-message').classList.add('hidden');
}

function hideLoading() {
    document.getElementById('loading').classList.add('hidden');
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function displayResults(data) {
    hideLoading();
    document.getElementById('upload-section').classList.add('hidden');
    document.getElementById('results-section').classList.remove('hidden');

    // Show navigation menu
    document.getElementById('side-nav').classList.remove('hidden');

    // Update file names in summary
    const fileCountElement = document.getElementById('file-count');
    const fileNameElement = document.getElementById('file-name');
    
    if (data.file_count && data.file_count > 1) {
        fileCountElement.textContent = data.file_count;
        // Show first few file names with tooltip for full list
        const displayNames = data.file_names.slice(0, 3).join(', ');
        const moreCount = data.file_names.length - 3;
        fileNameElement.textContent = moreCount > 0 ? 
            `${displayNames} and ${moreCount} more...` : displayNames;
        fileNameElement.title = data.file_names.join('\n');
    } else {
        fileCountElement.textContent = '1';
        fileNameElement.textContent = window.currentFileNames[0] || data.file_names[0] || 'Unknown';
    }

    // Update thread dump timestamp in summary
    const dumpTimestampElement = document.getElementById('dump-timestamp');
    if (data.statistics.timestamp) {
        dumpTimestampElement.textContent = data.statistics.timestamp;
    } else {
        dumpTimestampElement.textContent = 'Not available';
    }

    // Update Java version in summary
    const javaVersionElement = document.getElementById('java-version');
    if (data.statistics.java_version) {
        javaVersionElement.textContent = data.statistics.java_version;
    } else {
        javaVersionElement.textContent = 'Unknown';
    }
    
    // Update flamegraph title for burst mode
    const flamegraphTitle = document.getElementById('flamegraph-title');
    if (data.file_count && data.file_count > 1) {
        flamegraphTitle.textContent = `Stack Trace Flamegraph (Burst - ${data.file_count} files)`;
    } else {
        flamegraphTitle.textContent = 'Stack Trace Flamegraph';
    }

    // Update summary cards
    document.getElementById('total-threads').textContent = data.statistics.total_threads;
    
    // Show unique threads note for burst mode
    const uniqueThreadsNote = document.getElementById('unique-threads-note');
    if (data.file_count && data.file_count > 1 && data.statistics.unique_threads) {
        uniqueThreadsNote.textContent = `(${data.statistics.unique_threads} unique threads)`;
        uniqueThreadsNote.classList.remove('hidden');
    } else {
        uniqueThreadsNote.classList.add('hidden');
    }
    
    document.getElementById('daemon-threads').textContent = data.statistics.daemon_threads;
    document.getElementById('gc-threads').textContent = data.statistics.gc_threads || 0;
    document.getElementById('blocked-threads').textContent = data.blocked_threads;
    document.getElementById('waiting-threads').textContent = data.waiting_threads;
    document.getElementById('deadlock-count').textContent = data.total_deadlocks || data.deadlocks.length;

    // Render state distribution chart
    renderStateChart(data.statistics.state_distribution);

    // Render detailed state distribution chart
    renderDetailedStateChart(data.statistics.detailed_state_distribution);

    // Render thread pools chart and table
    renderPoolsSection(data.statistics.thread_pools, data.statistics.thread_pools_detailed);

    // Render flamegraph (prefer URL if available, fallback to inline SVG)
    if (data.flamegraph_url) {
        renderFlamegraph(data.flamegraph_url, true);
    } else {
        renderFlamegraph(data.flamegraph_svg, false);
    }
    
    // Render thread timeline (for burst mode)
    if (data.file_count && data.file_count > 1 && data.statistics.thread_timelines) {
        renderThreadTimeline(data.statistics.thread_timelines, data.file_names);
        document.getElementById('thread-timeline').classList.remove('hidden');
        document.getElementById('nav-timeline').classList.add('show');
        
        // Show flamegraph controls
        renderThreadFilter(data.statistics.thread_timelines);
        document.getElementById('flamegraph-controls').classList.remove('hidden');
    } else {
        document.getElementById('thread-timeline').classList.add('hidden');
        document.getElementById('nav-timeline').classList.remove('show');
        document.getElementById('flamegraph-controls').classList.add('hidden');
    }

    // Render deadlocks (both JVM-detected and potential deadlocks)
    renderDeadlocks(data.deadlocks, data.potential_deadlocks);

    // Render top CPU threads
    renderCpuThreads(data.top_cpu_threads);
}

function renderStateChart(stateDistribution) {
    const ctx = document.getElementById('state-chart').getContext('2d');

    // Prepare data
    const labels = Object.keys(stateDistribution);
    const values = Object.values(stateDistribution);

    // Color map for states
    const colorMap = {
        'RUNNABLE': '#22c55e',
        'BLOCKED': '#ef4444',
        'WAITING': '#f59e0b',
        'TIMED_WAITING': '#0ea5e9',
        'NEW': '#8b5cf6',
        'TERMINATED': '#64748b'
    };

    const colors = labels.map(label => colorMap[label] || '#64748b');

    // Create chart
    new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        font: {
                            size: 12
                        },
                        padding: 15
                    }
                },
                title: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderDetailedStateChart(detailedStateDistribution) {
    const ctx = document.getElementById('detailed-state-chart').getContext('2d');

    // Prepare data - sort by count for better visualization
    const sortedEntries = Object.entries(detailedStateDistribution).sort((a, b) => b[1] - a[1]);
    const labels = sortedEntries.map(entry => entry[0]);
    const values = sortedEntries.map(entry => entry[1]);

    // Color map for detailed states - group by base state
    const colorMap = {
        // RUNNABLE variants
        'RUNNABLE (Active)': '#22c55e',
        'RUNNABLE (Socket I/O)': '#4ade80',
        'RUNNABLE (File I/O)': '#86efac',

        // BLOCKED variants
        'BLOCKED (Monitor)': '#ef4444',

        // WAITING variants
        'WAITING (Parking)': '#f59e0b',
        'WAITING (Object.wait)': '#fbbf24',
        'WAITING (Condition)': '#fcd34d',
        'WAITING (Join)': '#fde68a',
        'WAITING (CountDownLatch)': '#fef3c7',
        'WAITING (Semaphore)': '#fff7ed',
        'WAITING (CyclicBarrier)': '#fef2f2',
        'WAITING (Other)': '#fed7aa',

        // TIMED_WAITING variants
        'TIMED_WAITING (Sleep)': '#0ea5e9',
        'TIMED_WAITING (Parking)': '#38bdf8',
        'TIMED_WAITING (Object.wait)': '#7dd3fc',
        'TIMED_WAITING (Join)': '#93c5fd',
        'TIMED_WAITING (Condition)': '#bae6fd',
        'TIMED_WAITING (Other)': '#cffafe',

        // JVM Internal Thread States (from raw_state)
        'Runnable': '#22c55e',
        'Waiting on condition': '#f59e0b',
        'In Object.wait()': '#fbbf24',
        'Waiting for monitor entry': '#ef4444',
        'Sleeping': '#0ea5e9',
        'Allocated': '#86efac',
        'Initialized': '#4ade80',
        'At breakpoint': '#8b5cf6',
        'Zombie': '#64748b',
        'Unknown state': '#94a3b8',

        // Other states
        'NEW': '#8b5cf6',
        'TERMINATED': '#64748b'
    };

    const colors = labels.map(label => colorMap[label] || '#94a3b8');

    // Create chart
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Thread Count',
                data: values,
                backgroundColor: colors,
                borderWidth: 1,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',  // Horizontal bar chart for better readability
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed.x || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return `Count: ${value} (${percentage}%)`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Thread Count'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Thread State'
                    }
                }
            }
        }
    });
}

function renderPoolsSection(threadPools, threadPoolsDetailed) {
    renderPoolsChart(threadPools);
    renderPoolsTable(threadPoolsDetailed);
}

function renderPoolsChart(threadPools) {
    const canvas = document.getElementById('pools-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Prepare data
    const labels = Object.keys(threadPools);
    const values = Object.values(threadPools);
    const total = values.reduce((a, b) => a + b, 0);

    // Generate colors for each pool
    const colors = [
        '#f59e0b', '#ef4444', '#3b82f6', '#06b6d4', '#14b8a6',
        '#8b5cf6', '#ec4899', '#f97316', '#eab308', '#22c55e',
        '#06b6d4', '#6366f1', '#a855f7', '#d946ef', '#f43f5e'
    ];

    // Create donut chart
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const percentage = ((value / total) * 100).toFixed(2);
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            },
            cutout: '60%'  // Donut hole size
        }
    });
}

function renderPoolsTable(threadPoolsDetailed) {
    const tbody = document.querySelector('#pools-table tbody');
    tbody.innerHTML = '';

    if (Object.keys(threadPoolsDetailed).length === 0) {
        tbody.innerHTML = '<tr><td colspan="3">No thread pools detected</td></tr>';
        return;
    }

    // Color map for state indicators - comprehensive coverage
    const stateColors = {
        // RUNNABLE variants
        'RUNNABLE (Active)': '#22c55e',
        'RUNNABLE (Socket I/O)': '#4ade80',
        'RUNNABLE (File I/O)': '#86efac',

        // BLOCKED variants
        'BLOCKED (Monitor)': '#ef4444',

        // WAITING variants
        'WAITING (Parking)': '#f59e0b',
        'WAITING (Object.wait)': '#fbbf24',
        'WAITING (Condition)': '#fcd34d',
        'WAITING (Join)': '#fde68a',
        'WAITING (CountDownLatch)': '#fef3c7',
        'WAITING (Semaphore)': '#fff7ed',
        'WAITING (CyclicBarrier)': '#fef2f2',
        'WAITING (Other)': '#fed7aa',

        // TIMED_WAITING variants
        'TIMED_WAITING (Sleep)': '#0ea5e9',
        'TIMED_WAITING (Parking)': '#38bdf8',
        'TIMED_WAITING (Object.wait)': '#7dd3fc',
        'TIMED_WAITING (Join)': '#93c5fd',
        'TIMED_WAITING (Condition)': '#bae6fd',
        'TIMED_WAITING (Other)': '#cffafe',

        // JVM Internal Thread States (from raw_state)
        'Runnable': '#22c55e',
        'Waiting on condition': '#f59e0b',
        'In Object.wait()': '#fbbf24',
        'Waiting for monitor entry': '#ef4444',
        'Sleeping': '#0ea5e9',
        'Allocated': '#86efac',
        'Initialized': '#4ade80',
        'At breakpoint': '#8b5cf6',
        'Zombie': '#64748b',
        'Unknown state': '#94a3b8',

        // Basic states (fallback)
        'RUNNABLE': '#22c55e',
        'BLOCKED': '#ef4444',
        'WAITING': '#f59e0b',
        'TIMED_WAITING': '#0ea5e9',
        'NEW': '#8b5cf6',
        'TERMINATED': '#64748b',

        'default': '#94a3b8'
    };

    for (const [poolName, states] of Object.entries(threadPoolsDetailed)) {
        const row = document.createElement('tr');

        // Calculate total count for this pool
        const totalCount = Object.values(states).reduce((a, b) => a + b, 0);

        // Create states HTML with colored dots
        const statesHtml = Object.entries(states)
            .sort((a, b) => b[1] - a[1])  // Sort by count descending
            .map(([state, count]) => {
                const color = stateColors[state] || stateColors['default'];
                // Shorten state name for display
                let shortState = state;
                if (state.includes('(')) {
                    shortState = state.split('(')[0].trim();
                }
                return `<span class="state-indicator" title="${escapeHtml(state)}: ${count} threads">
                    <span class="state-dot" style="background-color: ${color}"></span>
                    ${shortState}: ${count}
                </span>`;
            })
            .join(' ');

        row.innerHTML = `
            <td class="pool-name">${escapeHtml(poolName)}</td>
            <td>${totalCount}</td>
            <td class="states-column">${statesHtml}</td>
        `;
        tbody.appendChild(row);
    }
}

async function renderFlamegraph(svgContentOrUrl, isUrl) {
    const flamegraphDiv = document.getElementById('flamegraph');

    // Get SVG content
    let svgContent;
    if (isUrl) {
        try {
            const response = await fetch(svgContentOrUrl);
            if (!response.ok) {
                throw new Error('Failed to load flamegraph');
            }
            svgContent = await response.text();
        } catch (error) {
            console.error('Error loading flamegraph:', error);
            flamegraphDiv.innerHTML = `<p>Failed to load flamegraph: ${error.message}</p>`;
            return;
        }
    } else {
        svgContent = svgContentOrUrl;
    }

    // Create a minimal HTML document with the SVG embedded
    // This ensures the SVG's scripts can run in their own context
    const htmlContent = `
<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; padding: 0; overflow: hidden; display: flex; justify-content: center; }
        svg { display: block; max-width: 100%; height: auto; }
    </style>
</head>
<body>
${svgContent}
</body>
</html>
`;

    // Use iframe with srcdoc to provide isolated context where SVG scripts can run
    const iframe = document.createElement('iframe');
    iframe.style.width = '100%';
    iframe.style.height = 'auto';
    iframe.style.border = 'none';
    iframe.style.overflow = 'hidden';
    iframe.srcdoc = htmlContent;

    // Clear and append
    flamegraphDiv.innerHTML = '';
    flamegraphDiv.appendChild(iframe);

    // Adjust iframe height to match SVG content after it loads
    iframe.onload = function() {
        try {
            const svgDoc = iframe.contentDocument || iframe.contentWindow.document;
            const svg = svgDoc.querySelector('svg');
            if (svg) {
                const height = svg.getAttribute('height') || svg.clientHeight || '600';
                iframe.style.height = height + 'px';
            }
        } catch (e) {
            console.warn('Could not adjust iframe height:', e);
        }
    };
}

function renderDeadlocks(deadlocks, potentialDeadlocks) {
    const listDiv = document.getElementById('deadlocks-list');

    if (!listDiv) return;

    // Combine both types of deadlocks
    const hasJVMDeadlocks = deadlocks && deadlocks.length > 0;
    const hasPotentialDeadlocks = potentialDeadlocks && potentialDeadlocks.length > 0;

    if (!hasJVMDeadlocks && !hasPotentialDeadlocks) {
        listDiv.innerHTML = '<p style="color: var(--text-secondary);">No deadlocks detected</p>';
        return;
    }

    listDiv.innerHTML = '';

    // Render JVM-detected deadlocks
    if (hasJVMDeadlocks) {
        const jvmHeader = document.createElement('div');
        jvmHeader.className = 'deadlock-section-header';
        jvmHeader.innerHTML = '<h4>JVM-Detected Deadlocks</h4>';
        listDiv.appendChild(jvmHeader);

        deadlocks.forEach(deadlock => {
            const item = document.createElement('div');
            item.className = 'deadlock-item';

            const threadsDiv = document.createElement('div');
            threadsDiv.className = 'deadlock-threads';
            threadsDiv.textContent = `Threads involved: ${deadlock.threads.join(', ')}`;

            const descDiv = document.createElement('div');
            descDiv.className = 'deadlock-description';
            descDiv.textContent = deadlock.description;

            item.appendChild(threadsDiv);
            item.appendChild(descDiv);
            listDiv.appendChild(item);
        });
    }

    // Render potential deadlocks
    if (hasPotentialDeadlocks) {
        if (hasJVMDeadlocks) {
            const separator = document.createElement('hr');
            separator.className = 'deadlock-separator';
            listDiv.appendChild(separator);
        }

        const potentialHeader = document.createElement('div');
        potentialHeader.className = 'deadlock-section-header potential';
        potentialHeader.innerHTML = '<h4>Potential Deadlocks (Detected by Analysis)</h4>';
        listDiv.appendChild(potentialHeader);

        potentialDeadlocks.forEach(deadlock => {
            const item = document.createElement('div');
            item.className = 'deadlock-item potential';

            const typeDiv = document.createElement('div');
            typeDiv.className = 'deadlock-type';
            typeDiv.textContent = deadlock.type || 'Potential Deadlock';

            const threadsDiv = document.createElement('div');
            threadsDiv.className = 'deadlock-threads';
            threadsDiv.textContent = `Threads involved: ${deadlock.threads.join(', ')}`;

            const descDiv = document.createElement('div');
            descDiv.className = 'deadlock-description';
            descDiv.textContent = deadlock.description;

            item.appendChild(typeDiv);
            item.appendChild(threadsDiv);
            item.appendChild(descDiv);
            listDiv.appendChild(item);
        });
    }
}

function renderCpuThreads(cpuThreads) {
    const tbody = document.querySelector('#cpu-table tbody');
    tbody.innerHTML = '';

    if (!cpuThreads || cpuThreads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4">No CPU data available</td></tr>';
        return;
    }

    cpuThreads.forEach(thread => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="thread-name">${escapeHtml(thread.name)}</td>
            <td><span class="state-badge">${escapeHtml(thread.state)}</span></td>
            <td>${thread.cpu_time || 'N/A'}</td>
            <td><div class="stack-trace">${escapeHtml(thread.stack_trace.slice(0, 5).join('\n'))}</div></td>
        `;
        tbody.appendChild(row);
    });
}

function resetUpload() {
    document.getElementById('results-section').classList.add('hidden');
    document.getElementById('upload-section').classList.remove('hidden');
    document.getElementById('file-input').value = '';
    document.getElementById('error-message').classList.add('hidden');

    // Hide navigation menu
    document.getElementById('side-nav').classList.add('hidden');

    // Reset filenames
    window.currentFileNames = [];

    // Clear all charts
    const charts = ['state-chart', 'detailed-state-chart', 'pools-chart'];
    charts.forEach(chartId => {
        const canvas = document.getElementById(chartId);
        if (canvas) {
            const chartInstance = Chart.getChart(canvas);
            if (chartInstance) {
                chartInstance.destroy();
            }
        }
    });
}

// Navigation functions
function initializeNavigation() {
    // Add smooth scrolling to all navigation links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const targetElement = document.getElementById(targetId);

            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add scroll spy to highlight active navigation
    window.addEventListener('scroll', updateActiveNavigation);
}

function updateActiveNavigation() {
    const sections = ['summary', 'state-distribution', 'thread-pools', 'flamegraph', 'thread-timeline', 'deadlocks', 'top-cpu'];
    const navLinks = document.querySelectorAll('.nav-link');

    let currentSection = '';

    sections.forEach(sectionId => {
        const section = document.getElementById(sectionId);
        if (section && !section.classList.contains('hidden')) {
            const rect = section.getBoundingClientRect();
            // Check if section is in viewport
            if (rect.top <= 150 && rect.bottom >= 150) {
                currentSection = sectionId;
            }
        }
    });

    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === `#${currentSection}`) {
            link.classList.add('active');
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderThreadTimeline(timelines, fileNames) {
    const tbody = document.querySelector('#timeline-table tbody');
    tbody.innerHTML = '';
    
    if (!timelines || timelines.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6">No thread timeline data available</td></tr>';
        return;
    }
    
    // Store timelines globally for filtering
    window.threadTimelines = timelines;
    window.dumpFileNames = fileNames;
    
    // Render all timelines
    renderTimelineRows(timelines, fileNames);
    
    // Setup search
    document.getElementById('timeline-search').addEventListener('input', filterTimelines);
    document.getElementById('show-multi-dump-only').addEventListener('change', filterTimelines);
}

function renderTimelineRows(timelines, fileNames) {
    const tbody = document.querySelector('#timeline-table tbody');
    tbody.innerHTML = '';
    
    timelines.forEach(timeline => {
        const row = document.createElement('tr');
        
        // Thread name
        const nameCell = document.createElement('td');
        nameCell.textContent = timeline.name;
        nameCell.className = 'thread-name';
        row.appendChild(nameCell);
        
        // Thread ID
        const idCell = document.createElement('td');
        idCell.textContent = timeline.thread_id;
        idCell.style.fontSize = '0.85rem';
        idCell.style.color = 'var(--text-secondary)';
        row.appendChild(idCell);
        
        // Instance count
        const instanceCell = document.createElement('td');
        instanceCell.textContent = timeline.instances.length;
        row.appendChild(instanceCell);
        
        // Dumps
        const dumpsCell = document.createElement('td');
        timeline.dump_indices.forEach(idx => {
            const badge = document.createElement('span');
            badge.className = 'thread-dumps-badge';
            badge.textContent = idx + 1;
            badge.title = fileNames[idx];
            dumpsCell.appendChild(badge);
        });
        row.appendChild(dumpsCell);
        
        // Unique stacks
        const stacksCell = document.createElement('td');
        stacksCell.textContent = timeline.unique_stacks || timeline.instances.length;
        row.appendChild(stacksCell);
        
        // Actions
        const actionsCell = document.createElement('td');
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn-view-thread';
        viewBtn.textContent = 'View Details';
        viewBtn.onclick = () => showThreadDetails(timeline);
        actionsCell.appendChild(viewBtn);
        row.appendChild(actionsCell);
        
        tbody.appendChild(row);
    });
}

function filterTimelines() {
    const searchTerm = document.getElementById('timeline-search').value.toLowerCase();
    const multiDumpOnly = document.getElementById('show-multi-dump-only').checked;
    
    let filtered = window.threadTimelines;
    
    if (searchTerm) {
        filtered = filtered.filter(t => 
            t.name.toLowerCase().includes(searchTerm) || 
            t.thread_id.toLowerCase().includes(searchTerm)
        );
    }
    
    if (multiDumpOnly) {
        filtered = filtered.filter(t => t.instances.length > 1);
    }
    
    renderTimelineRows(filtered, window.dumpFileNames);
}

function showThreadDetails(timeline) {
    alert(`Thread: ${timeline.name}\nID: ${timeline.thread_id}\nInstances: ${timeline.instances.length}\nDumps: ${timeline.dump_indices.map(i => i+1).join(', ')}\nUnique Stacks: ${timeline.unique_stacks || timeline.instances.length}`);
    // TODO: Show detailed modal with stack traces
}

function renderThreadFilter(timelines) {
    const select = document.getElementById('thread-filter');
    select.innerHTML = '<option value="">All Threads (Cumulative)</option>';
    
    // Add option for each unique thread
    timelines.forEach(timeline => {
        const option = document.createElement('option');
        option.value = timeline.thread_id;
        option.textContent = `${timeline.name} (${timeline.instances.length} instances)`;
        select.appendChild(option);
    });
    
    // Handle filter change
    select.addEventListener('change', function() {
        const threadId = this.value;
        const info = document.getElementById('thread-info');
        
        if (threadId) {
            const timeline = timelines.find(t => t.thread_id === threadId);
            if (timeline) {
                info.textContent = `Showing ${timeline.instances.length} instances across dumps ${timeline.dump_indices.map(i => i+1).join(', ')}`;
            }
            // TODO: Filter flamegraph to show only this thread
        } else {
            info.textContent = '';
        }
    });
}
