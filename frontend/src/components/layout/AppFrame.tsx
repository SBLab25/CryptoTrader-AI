"use client";

import { usePathname } from "next/navigation";

import { Sidebar } from "@/components/layout/Sidebar";
import { BootstrapData } from "@/components/layout/BootstrapData";
import { Toaster } from "@/components/ui/Toaster";

export function AppFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  return (
    <>
      {!isLogin && <BootstrapData />}
      <div className={isLogin ? "min-h-screen" : "min-h-screen bg-[#09090d]"}>
        {isLogin ? (
          children
        ) : (
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 min-w-0">{children}</main>
          </div>
        )}
      </div>
      <Toaster />
    </>
  );
}
