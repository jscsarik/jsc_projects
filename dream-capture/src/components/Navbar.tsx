import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../lib/utils';

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false);
  const location = useLocation();

  // Close mobile menu when route changes
  useEffect(() => {
    setIsOpen(false);
  }, [location]);

  const navLinks = [
    { name: '홈', path: '/' },
    { name: '소개', path: '/about' },
    { name: '포트폴리오', path: '/portfolio' },
    { name: '가격 안내', path: '/pricing' },
    { name: '예약 안내', path: '/reservation' },
    { name: 'FAQ', path: '/faq' },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#F5F2EB]/90 backdrop-blur-md border-b border-[#3A3532]/5 transition-all duration-300">
      <div className="container mx-auto px-6 h-24 flex items-center justify-between">
        {/* Logo */}
        <Link 
          to="/" 
          className="flex flex-col items-start group"
        >
          <span className="text-2xl font-serif tracking-tighter text-[#2A2522] group-hover:opacity-70 transition-opacity font-light">
            이재호 필름
          </span>
          <span className="text-[9px] tracking-[0.25em] text-[#8C7B75] uppercase mt-1 font-light opacity-80">
            Lee Jaeho Film
          </span>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden md:flex items-center gap-14">
          {navLinks.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              className={cn(
                "text-[13px] font-light tracking-[0.15em] hover:text-[#8C7B75] transition-all duration-300 relative py-1 after:content-[''] after:absolute after:bottom-0 after:left-0 after:w-0 after:h-[1px] after:bg-[#8C7B75] after:transition-all after:duration-300 hover:after:w-full",
                location.pathname === link.path ? "text-[#2A2522] font-normal after:w-full" : "text-[#5D5D5D]"
              )}
            >
              {link.name}
            </Link>
          ))}
        </div>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2 text-[#3A3532] hover:bg-[#3A3532]/5 rounded-sm transition-colors"
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Toggle menu"
        >
          {isOpen ? <X size={22} strokeWidth={1} /> : <Menu size={22} strokeWidth={1} />}
        </button>
      </div>

      {/* Mobile Navigation Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-[#F5F2EB] border-b border-[#3A3532]/10 overflow-hidden"
          >
            <div className="flex flex-col px-6 py-10 gap-8 items-center">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  className={cn(
                    "text-lg font-serif font-light hover:text-[#8C7B75] transition-colors tracking-wide",
                    location.pathname === link.path ? "text-[#2A2522]" : "text-[#5D5D5D]"
                  )}
                >
                  {link.name}
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
