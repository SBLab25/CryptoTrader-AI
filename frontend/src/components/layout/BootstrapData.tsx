"use client";

import { useEffect } from "react";

import { approvals, auth, risk, system, training } from "@/lib/api";
import { portfolioApi } from "@/lib/api";
import { connectWS, disconnectWS, useStore } from "@/store";

export function BootstrapData() {
  const setStatus = useStore((state) => state.setStatus);
  const setPortfolio = useStore((state) => state.setPortfolio);
  const setPositions = useStore((state) => state.setPositions);
  const setRiskStatus = useStore((state) => state.setRiskStatus);
  const setApprovals = useStore((state) => state.setApprovals);
  const setTrainingStatus = useStore((state) => state.setTrainingStatus);

  useEffect(() => {
    let active = true;

    async function boot() {
      try {
        await auth.me();
        const [status, portfolio, positions, riskStatus, pendingApprovals, trainingStatus, wsToken] =
          await Promise.all([
            system.status(),
            portfolioApi.summary(),
            portfolioApi.positions(),
            risk.status(),
            approvals.pending(),
            training.status(),
            auth.wsToken()
          ]);

        if (!active) {
          return;
        }

        setStatus(status);
        setPortfolio(portfolio);
        setPositions(positions);
        setRiskStatus(riskStatus);
        setApprovals(pendingApprovals);
        setTrainingStatus(trainingStatus);
        connectWS(wsToken.token);
      } catch {
        // The middleware handles redirects; we stay quiet here.
      }
    }

    void boot();

    return () => {
      active = false;
      disconnectWS();
    };
  }, [setApprovals, setPortfolio, setPositions, setRiskStatus, setStatus, setTrainingStatus]);

  return null;
}
