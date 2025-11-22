# Frontend Polling Example - Level 2 Async Deep-Dive

## Overview

The Level 2 Deep-Dive Analysis now **automatically fetches fresh Trendlyne data** before running analysis. This takes 60-120 seconds, so the API uses an async pattern:

1. **Initiate** analysis → Get `analysis_id` immediately
2. **Poll** status endpoint → Check progress
3. **Receive** completed report → Display to user

---

## Complete JavaScript Example

```javascript
/**
 * Level 2 Deep-Dive Analysis with Polling
 *
 * This function handles the complete flow:
 * - Initiates deep-dive analysis
 * - Polls for completion
 * - Updates UI with progress
 * - Displays final report
 */

async function runLevel2DeepDive(symbol, expiryDate, level1Results) {
    try {
        // Step 1: Initiate analysis (returns immediately)
        showLoadingState('Initiating deep-dive analysis...');

        const response = await fetch('/api/trading/futures/deep-dive/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getAuthToken()}`
            },
            body: JSON.stringify({
                symbol: symbol,
                expiry_date: expiryDate,
                level1_results: level1Results
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to initiate analysis: ${response.statusText}`);
        }

        const { analysis_id, poll_url, estimated_time, message } = await response.json();

        console.log(`Analysis initiated (ID: ${analysis_id})`);
        console.log(`Estimated time: ${estimated_time}`);

        // Step 2: Poll for completion
        const report = await pollForCompletion(analysis_id, poll_url);

        // Step 3: Display report
        displayDeepDiveReport(report);

        return report;

    } catch (error) {
        console.error('Deep-dive analysis failed:', error);
        showError(`Analysis failed: ${error.message}`);
        throw error;
    }
}


/**
 * Poll the status endpoint until analysis completes
 */
async function pollForCompletion(analysisId, pollUrl) {
    const POLL_INTERVAL = 3000;  // 3 seconds
    const MAX_ATTEMPTS = 60;     // 3 minutes max (60 * 3s)

    let attempts = 0;

    while (attempts < MAX_ATTEMPTS) {
        attempts++;

        // Wait before polling
        await sleep(POLL_INTERVAL);

        // Check status
        const statusResponse = await fetch(pollUrl, {
            headers: {
                'Authorization': `Bearer ${getAuthToken()}`
            }
        });

        if (!statusResponse.ok) {
            throw new Error(`Status check failed: ${statusResponse.statusText}`);
        }

        const statusData = await statusResponse.json();

        if (statusData.status === 'COMPLETED') {
            // Analysis complete!
            console.log('Analysis completed successfully');
            hideLoadingState();
            return statusData.report;

        } else if (statusData.status === 'FAILED') {
            // Analysis failed
            hideLoadingState();
            throw new Error(statusData.error || 'Analysis failed');

        } else if (statusData.status === 'PROCESSING') {
            // Still processing - update UI
            const { message, progress } = statusData;
            updateLoadingState(message, progress);
            console.log(`Progress: ${progress}% - ${message}`);

        } else {
            // Unknown status
            console.warn('Unknown status:', statusData.status);
        }
    }

    // Timeout
    hideLoadingState();
    throw new Error('Analysis timed out after 3 minutes');
}


/**
 * Display the completed deep-dive report
 */
function displayDeepDiveReport(report) {
    const { executive_summary, detailed_analysis, trading_recommendation, decision_matrix } = report;

    // Clear loading state
    hideLoadingState();

    // Display executive summary
    displayExecutiveSummary(executive_summary);

    // Display detailed analysis tabs
    displayDetailedAnalysis(detailed_analysis);

    // Display trading recommendations
    displayTradingRecommendation(trading_recommendation);

    // Display decision matrix
    displayDecisionMatrix(decision_matrix);

    // Show action buttons (Execute/Modify/Reject)
    showDecisionButtons();
}


// Helper functions

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getAuthToken() {
    // Get your auth token from storage/state
    return localStorage.getItem('authToken');
}

function showLoadingState(message) {
    // Show loading overlay with message
    const loadingDiv = document.getElementById('loading-overlay');
    loadingDiv.innerHTML = `
        <div class="loading-spinner"></div>
        <p>${message}</p>
        <div class="progress-bar">
            <div id="progress-fill" style="width: 0%"></div>
        </div>
        <p id="progress-text">0%</p>
    `;
    loadingDiv.style.display = 'block';
}

function updateLoadingState(message, progress) {
    // Update loading message and progress
    const loadingDiv = document.getElementById('loading-overlay');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    loadingDiv.querySelector('p').textContent = message;
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${progress}%`;
}

function hideLoadingState() {
    const loadingDiv = document.getElementById('loading-overlay');
    loadingDiv.style.display = 'none';
}

function showError(message) {
    alert(message);  // Or use a better error UI
}

// Display functions (customize based on your UI framework)

function displayExecutiveSummary(summary) {
    console.log('Executive Summary:', summary);
    // Display: one_line_verdict, conviction_score, key_strengths, key_concerns, etc.
}

function displayDetailedAnalysis(analysis) {
    console.log('Detailed Analysis:', analysis);
    // Display tabs: Financial, Valuation, Institutional, Technical, Risk
}

function displayTradingRecommendation(recommendation) {
    console.log('Trading Recommendation:', recommendation);
    // Display: entry_strategy, position_sizing, stop_loss, profit_targets
}

function displayDecisionMatrix(matrix) {
    console.log('Decision Matrix:', matrix);
    // Display: bullish_factors, bearish_factors, risks, catalysts
}

function showDecisionButtons() {
    // Show Execute/Modify/Reject buttons
    const buttonsDiv = document.getElementById('decision-buttons');
    buttonsDiv.innerHTML = `
        <button onclick="recordDecision('EXECUTED')">Execute Trade</button>
        <button onclick="recordDecision('MODIFIED')">Modify & Execute</button>
        <button onclick="recordDecision('REJECTED')">Reject</button>
    `;
    buttonsDiv.style.display = 'block';
}
```

---

## React Example

If you're using React:

```jsx
import React, { useState } from 'react';

function Level2DeepDive({ symbol, expiryDate, level1Results }) {
    const [loading, setLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [message, setMessage] = useState('');
    const [report, setReport] = useState(null);
    const [error, setError] = useState(null);

    const runDeepDive = async () => {
        setLoading(true);
        setError(null);
        setProgress(0);
        setMessage('Initiating deep-dive analysis...');

        try {
            // Initiate analysis
            const initResponse = await fetch('/api/trading/futures/deep-dive/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getAuthToken()}`
                },
                body: JSON.stringify({
                    symbol,
                    expiry_date: expiryDate,
                    level1_results: level1Results
                })
            });

            const { analysis_id, poll_url } = await initResponse.json();

            // Poll for completion
            const completedReport = await pollStatus(poll_url);

            setReport(completedReport);
            setLoading(false);

        } catch (err) {
            setError(err.message);
            setLoading(false);
        }
    };

    const pollStatus = async (pollUrl) => {
        while (true) {
            await new Promise(resolve => setTimeout(resolve, 3000));

            const statusResponse = await fetch(pollUrl, {
                headers: {
                    'Authorization': `Bearer ${getAuthToken()}`
                }
            });

            const statusData = await statusResponse.json();

            if (statusData.status === 'COMPLETED') {
                return statusData.report;
            } else if (statusData.status === 'FAILED') {
                throw new Error(statusData.error);
            } else {
                setMessage(statusData.message);
                setProgress(statusData.progress);
            }
        }
    };

    return (
        <div>
            {!loading && !report && (
                <button onClick={runDeepDive}>
                    Run Deep-Dive Analysis
                </button>
            )}

            {loading && (
                <div className="loading-state">
                    <div className="spinner"></div>
                    <p>{message}</p>
                    <div className="progress-bar">
                        <div
                            className="progress-fill"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                    <p>{progress}%</p>
                </div>
            )}

            {error && (
                <div className="error">
                    Error: {error}
                </div>
            )}

            {report && (
                <DeepDiveReportDisplay report={report} />
            )}
        </div>
    );
}
```

---

## CSS for Loading State

```css
#loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    z-index: 9999;
    color: white;
}

.loading-spinner {
    border: 4px solid #f3f3f3;
    border-top: 4px solid #3498db;
    border-radius: 50%;
    width: 50px;
    height: 50px;
    animation: spin 1s linear infinite;
    margin-bottom: 20px;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.progress-bar {
    width: 300px;
    height: 20px;
    background: #333;
    border-radius: 10px;
    overflow: hidden;
    margin: 20px 0 10px 0;
}

#progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3498db, #2ecc71);
    transition: width 0.5s ease;
}

#progress-text {
    font-size: 14px;
    margin-top: 5px;
}
```

---

## API Flow Diagram

```
User clicks "Deep-Dive" button
         |
         v
POST /api/trading/futures/deep-dive/
         |
         v
Response: {
    analysis_id: 123,
    status: 'PROCESSING',
    poll_url: '/api/trading/deep-dive/123/status/'
}
         |
         v
[Frontend enters polling loop]
         |
         v
GET /api/trading/deep-dive/123/status/  (every 3 seconds)
         |
         v
Response: {
    status: 'PROCESSING',
    message: 'Downloading latest Trendlyne data...',
    progress: 33
}
         |
         v
[Continue polling...]
         |
         v
Response: {
    status: 'PROCESSING',
    message: 'Running comprehensive analysis...',
    progress: 66
}
         |
         v
[Continue polling...]
         |
         v
Response: {
    status: 'COMPLETED',
    report: { ... full report ... }
}
         |
         v
[Display report to user]
```

---

## Progress Messages You'll See

Based on the backend implementation:

1. **33% Progress**: "Downloading latest Trendlyne data..."
2. **66% Progress**: "Running comprehensive multi-factor analysis..."
3. **100% Progress**: "COMPLETED" status with full report

---

## Error Handling

```javascript
// Handle different error scenarios

try {
    const report = await runLevel2DeepDive(symbol, expiryDate, level1Results);
} catch (error) {
    if (error.message.includes('timeout')) {
        // Analysis took too long
        showError('Analysis is taking longer than expected. Please try again later.');
    } else if (error.message.includes('Failed to initiate')) {
        // Problem starting analysis
        showError('Could not start analysis. Please check your inputs and try again.');
    } else if (error.message.includes('Trendlyne')) {
        // Data fetch failed
        showError('Could not fetch latest market data. Analysis will use existing data.');
    } else {
        // Generic error
        showError(`Analysis failed: ${error.message}`);
    }
}
```

---

## Testing the Flow

Use browser console to test:

```javascript
// Test the polling flow
const testData = {
    symbol: 'RELIANCE',
    expiry_date: '2024-01-25',
    level1_results: {
        verdict: 'PASS',
        composite_score: 72,
        direction: 'LONG'
    }
};

runLevel2DeepDive('RELIANCE', '2024-01-25', testData)
    .then(report => console.log('Report:', report))
    .catch(error => console.error('Error:', error));
```

---

## Summary

**Key Points:**

1. ✅ Backend automatically fetches fresh Trendlyne data (60-120 seconds)
2. ✅ Frontend gets immediate response with `analysis_id`
3. ✅ Frontend polls every 3 seconds for status updates
4. ✅ Progress updates keep user informed (33%, 66%, 100%)
5. ✅ Completed report is displayed when ready
6. ✅ Errors are handled gracefully

**Expected User Experience:**

1. User clicks "Deep-Dive Analysis" button
2. Loading overlay appears: "Downloading latest Trendlyne data..."
3. Progress bar updates to 33%
4. Message changes: "Running comprehensive analysis..."
5. Progress bar updates to 66%
6. Loading disappears, comprehensive report is displayed
7. User reviews and makes decision (Execute/Modify/Reject)

Total wait time: **60-120 seconds** (mostly for fresh data fetching)
