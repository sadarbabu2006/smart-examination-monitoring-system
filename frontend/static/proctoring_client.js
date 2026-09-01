/**
 * Browser-Side Examination Proctoring Client
 * 
 * Captures real client-side events:
 * 1. Tab switches (via document visibilitychange API)
 * 2. Focus loss (via window blur API)
 * 3. Focus regain (via window focus API)
 * 
 * Dispatches structured telemetry payloads to the backend `/api/monitoring/events` endpoint.
 */

class ProctoringClient {
    constructor(sessionId, apiBaseUrl = "") {
        if (!sessionId) {
            throw new Error("ProctoringClient requires an active sessionId");
        }
        this.sessionId = sessionId;
        this.apiBaseUrl = apiBaseUrl.replace(/\/$/, "");
        this.tabSwitchCount = 0;
        this.focusLossCount = 0;
        this.isMonitoring = false;

        this._onVisibilityChange = this._onVisibilityChange.bind(this);
        this._onWindowBlur = this._onWindowBlur.bind(this);
        this._onWindowFocus = this._onWindowFocus.bind(this);
    }

    start() {
        if (this.isMonitoring) return;
        this.isMonitoring = true;

        document.addEventListener("visibilitychange", this._onVisibilityChange);
        window.addEventListener("blur", this._onWindowBlur);
        window.addEventListener("focus", this._onWindowFocus);

        console.log(`[ProctoringClient] Monitoring initialized for Session #${this.sessionId}`);
    }

    stop() {
        if (!this.isMonitoring) return;
        this.isMonitoring = false;

        document.removeEventListener("visibilitychange", this._onVisibilityChange);
        window.removeEventListener("blur", this._onWindowBlur);
        window.removeEventListener("focus", this._onWindowFocus);

        console.log(`[ProctoringClient] Monitoring stopped for Session #${this.sessionId}`);
    }

    _onVisibilityChange() {
        if (document.hidden || document.visibilityState === "hidden") {
            this.tabSwitchCount += 1;
            console.warn(`[ProctoringClient] Tab switch detected (${this.tabSwitchCount})`);
            this.sendTelemetry("tab_switch", {
                tab_switch_number: this.tabSwitchCount,
                visibility_state: document.visibilityState,
                timestamp: new Date().toISOString()
            });
        }
    }

    _onWindowBlur() {
        this.focusLossCount += 1;
        console.warn(`[ProctoringClient] Focus loss detected (${this.focusLossCount})`);
        this.sendTelemetry("focus_loss", {
            focus_loss_number: this.focusLossCount,
            timestamp: new Date().toISOString()
        });
    }

    _onWindowFocus() {
        this.sendTelemetry("focus_regained", {
            timestamp: new Date().toISOString()
        });
    }

    async sendTelemetry(eventType, details = {}) {
        const payload = {
            session_id: this.sessionId,
            event_type: eventType,
            timestamp: new Date().toISOString(),
            details: details
        };

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/monitoring/events`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload),
                credentials: "include"
            });

            if (!response.ok) {
                console.error(`[ProctoringClient] Failed to send telemetry: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error("[ProctoringClient] Network error sending telemetry:", error);
        }
    }
}

if (typeof window !== "undefined") {
    window.ProctoringClient = ProctoringClient;
}
