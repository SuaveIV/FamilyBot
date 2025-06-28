document.addEventListener('DOMContentLoaded', function() {
    const commandButtons = document.querySelectorAll('.admin-command-btn');
    const commandOutput = document.getElementById('command-output');
    const dealsTargetUser = document.getElementById('deals-target-user');
    const forceDealsBtn = document.getElementById('force-deals-btn');

    // Load family members for the dropdown
    loadFamilyMembers();

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
            let requestBody = {};

            if (endpoint.includes('plugin-action')) {
                url = `${endpoint}?command_name=${command}`;
                
                // Special handling for force_deals command
                if (command === 'force_deals' && dealsTargetUser) {
                    const selectedUser = dealsTargetUser.value;
                    if (selectedUser) {
                        url += `&target_user=${encodeURIComponent(selectedUser)}`;
                    }
                }
            }

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            })
            .then(response => response.json())
            .then(data => {
                let outputHtml = `<h3>${commandName} Result:</h3>`;
                if (data.success) {
                    outputHtml += `<div class="alert alert-success">${formatMessage(data.message)}</div>`;
                } else {
                    outputHtml += `<div class="alert alert-danger">${formatMessage(data.message)}</div>`;
                }
                commandOutput.innerHTML = outputHtml;
            })
            .catch(error => {
                commandOutput.innerHTML = `<h3>Error:</h3><div class="alert alert-danger">An error occurred while executing the command: ${error}</div>`;
            })
            .finally(() => {
                // Re-enable all buttons
                commandButtons.forEach(btn => btn.disabled = false);
            });
        });
    });

    async function loadFamilyMembers() {
        try {
            const response = await fetch('/api/family-members');
            const familyMembers = await response.json();
            
            if (dealsTargetUser && familyMembers.length > 0) {
                // Clear existing options except the first one
                dealsTargetUser.innerHTML = '<option value="">All Family Members</option>';
                
                // Add family members to dropdown
                familyMembers.forEach(member => {
                    const option = document.createElement('option');
                    option.value = member.friendly_name;
                    option.textContent = member.friendly_name;
                    dealsTargetUser.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading family members:', error);
        }
    }

    function formatMessage(message) {
        // Convert newlines to <br> tags and preserve formatting
        return message
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Bold text
            .replace(/~~(.*?)~~/g, '<del>$1</del>') // Strikethrough
            .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>'); // Links
    }
});
