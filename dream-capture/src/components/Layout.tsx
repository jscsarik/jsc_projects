import React from 'react';
import { Camera } from 'lucide-react';
import Navbar from './Navbar';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground selection:bg-white selection:text-black">
      <Navbar />

      <main className="flex-grow pt-20">
        {children}
      </main>

      <footer className="py-12 border-t border-[#3A3532]/10 bg-[#F5F2EB]">
        <div className="container mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-6 text-[#8C7B75]">
          <div className="flex flex-col md:items-start items-center gap-1">
            <p className="text-[10px] font-light tracking-[0.2em] uppercase">Lee Jaeho Film</p>
            <p className="text-xs font-light tracking-wide text-[#5D5D5D]">© 2026 이재호 필름. All rights reserved.</p>
          </div>
          <div className="flex gap-6 opacity-70 hover:opacity-100 transition-opacity">
            <a href="#" className="hover:text-[#3A3532] transition-colors"><Camera size={16} strokeWidth={1} /></a>
          </div>
        </div>
      </footer>
    </div>
  );
}
