document.addEventListener('DOMContentLoaded', async () => {
    // Ensure currentProjectId is defined in the HTML before this script runs
    if (typeof currentProjectId === 'undefined' || currentProjectId === null) {
        console.error("Project ID is not defined. Cannot load budget.");
        return;
    }
    await fetchPredictedBudget();
    await fetchExpenses();
    await fetchHistory(); // Fetch and display chat history
    updateRemainingBudget();

    document.getElementById('expense-form').addEventListener('submit', addExpense);
    document.getElementById('copilot-form').addEventListener('submit', handleCopilotSubmit);
});

async function fetchPredictedBudget() {
    try {
        const predictResponse = await fetch(`/api/budget/predict/${currentProjectId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: currentProjectId })
        });
        const predictionData = await predictResponse.json();
        const predictedBudgetValue = predictionData.predicted_budget ? `${predictionData.predicted_budget.toLocaleString()}` : '$0';
        document.getElementById('forecasted-budget').value = predictedBudgetValue;
        document.getElementById('ml-prediction').textContent = predictedBudgetValue;
    } catch (error) {
        console.error("Error fetching predicted budget:", error);
        document.getElementById('forecasted-budget').value = '$0';
    }
}

async function fetchExpenses() {
    try {
        const response = await fetch(`/api/budget/expenses/${currentProjectId}`);
        const expenses = await response.json();
        const expenseList = document.getElementById('expense-list');
        expenseList.innerHTML = '';
        let totalSpent = 0;
        expenses.forEach(expense => {
            const li = document.createElement('li');
            li.innerHTML = `<span>${expense.description}</span> <span>$${expense.amount.toLocaleString()}</span>
                            <button onclick="deleteExpense(${expense.id})">Delete</button>`;
            expenseList.appendChild(li);
            totalSpent += expense.amount;
        });
        document.getElementById('total-spent').textContent = `$${totalSpent.toLocaleString()}`;
        updateRemainingBudget();
    } catch (error) {
        console.error("Error fetching expenses:", error);
    }
}

async function addExpense(event) {
    event.preventDefault();
    const description = document.getElementById('expense-description').value;
    const amount = parseFloat(document.getElementById('expense-amount').value);

    if (!description || isNaN(amount)) {
        alert("Please provide a valid description and amount.");
        return;
    }

    try {
        await fetch(`/api/budget/expenses/${currentProjectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({description, amount})
        });
        document.getElementById('expense-form').reset();
        fetchExpenses(); // Refresh the list
    } catch (error) {
        console.error("Error adding expense:", error);
    }
}

async function deleteExpense(expenseId) {
    if (!confirm("Are you sure you want to delete this expense?")) {
        return;
    }
    try {
        await fetch(`/api/budget/expenses/${currentProjectId}`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: expenseId})
        });
        fetchExpenses(); // Refresh the list
    } catch (error) {
        console.error("Error deleting expense:", error);
    }
}

function handleBudgetInput(event) {
    const subtitle = document.querySelector('.subtitle');
    const restoreButton = document.getElementById('restore-button');
    if (event.target.value) {
        subtitle.style.display = 'none';
        restoreButton.style.display = 'inline-block';
    } else {
        subtitle.style.display = 'inline';
        restoreButton.style.display = 'none';
    }
    updateRemainingBudget();
}

function restorePrediction() {
    const mlPrediction = document.getElementById('ml-prediction').textContent;
    document.getElementById('forecasted-budget').value = mlPrediction;
    document.getElementById('restore-button').style.display = 'none';
    document.querySelector('.subtitle').style.display = 'inline';
    updateRemainingBudget();
}

function updateRemainingBudget() {
    const forecasted = parseFloat(document.getElementById('forecasted-budget').value.replace(/[^0-9.-]+/g, ""));
    const spent = parseFloat(document.getElementById('total-spent').textContent.replace(/[^0-9.-]+/g, ""));
    const remaining = forecasted - spent;
    document.getElementById('remaining-budget').textContent = `$${remaining.toLocaleString()}`;
}

async function fetchHistory() {
    try {
        const response = await fetch(`/api/budget/copilot/history/${currentProjectId}`);
        const history = await response.json();
        const chatWindow = document.getElementById('copilot-chat-window');
        chatWindow.innerHTML = ''; // Clear the initial message
        history.forEach(message => {
            addMessageToChatWindow(message.text, message.role);
        });
    } catch (error) {
        console.error("Error fetching chat history:", error);
    }
}

async function handleCopilotSubmit(event) {
    event.preventDefault();
    const input = document.getElementById('copilot-input');
    const message = input.value.trim();
    if (!message) return;

    addMessageToChatWindow(message, 'user');
    input.value = '';

    // Add a thinking indicator
    addMessageToChatWindow('...', 'ai', true);

    try {
        // We need to send the current budget context to the AI
        const forecasted = parseFloat(document.getElementById('forecasted-budget').value.replace(/[^0-9.-]+/g, ""));
        const expenses = [];
        document.querySelectorAll('#expense-list li').forEach(item => {
            const description = item.querySelector('span:first-child').textContent;
            const amount = parseFloat(item.querySelector('span:nth-child(2)').textContent.replace(/[^0-9.-]+/g, ""));
            expenses.push({ description, amount });
        });

        const response = await fetch(`/api/budget/copilot/${currentProjectId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                budget: {
                    forecasted: forecasted,
                    expenses: expenses
                }
            })
        });
        const data = await response.json();
        removeThinkingIndicator();
        addMessageToChatWindow(data.reply, 'ai');

        // Handle actions
        if (data.action) {
            if (data.action.type === 'add_item') {
                // The backend already added the item to the DB,
                // so we just need to refresh the list.
                fetchExpenses();
            }
            // Future actions like 'delete_item' or 'update_item' would be handled here
        }

    } catch (error) {
        console.error("Error with AI Copilot:", error);
        removeThinkingIndicator();
        addMessageToChatWindow('Sorry, I am having trouble connecting to the AI. Please try again later.', 'ai');
    }
}

function addMessageToChatWindow(message, sender, isThinking = false) {
    const chatWindow = document.getElementById('copilot-chat-window');
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${sender}-message`);
    if (isThinking) {
        messageElement.id = 'thinking-indicator';
    }
    const p = document.createElement('p');
    p.textContent = message;
    messageElement.appendChild(p);
    chatWindow.appendChild(messageElement);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function removeThinkingIndicator() {
    const indicator = document.getElementById('thinking-indicator');
    if (indicator) {
        indicator.remove();
    }
}