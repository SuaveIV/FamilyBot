document.addEventListener('DOMContentLoaded', function() {
    const commandButtons = document.querySelectorAll('.admin-command-btn');
    const commandOutput = document.getElementById('command-output');

    commandButtons.forEach(button => {
        button.addEventListener('click', function() {
            const command = this.dataset.command;
            const commandName = this.textContent.trim();
            const endpoint = this.dataset.endpoint;

            // Disable all buttons to prevent multiple commands from running
            commandButtons.forEach(btn => btn.disabled = true);
            
            // Show loading message
            commandOutput.innerHTML = `<p>Executing "${commandName}"...</p>`;

            let url = endpoint;
            if (endpoint.includes('plugin-action')) {
                url = `${endpoint}?command_name=${command}`;
            }

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                let outputHtml = `<h3>${commandName} Result:</h3>`;
                if (data.success) {
                    outputHtml += `<p class="success">${data.message}</p>`;
                } else {
                    outputHtml += `<p class="error">${data.message}</p>`;
                }
                commandOutput.innerHTML = outputHtml;
            })
            .catch(error => {
                commandOutput.innerHTML = `<h3>Error:</h3><p class="error">An error occurred while executing the command: ${error}</p>`;
            })
            .finally(() => {
                // Re-enable all buttons
                commandButtons.forEach(btn => btn.disabled = false);
            });
        });
    });
});
