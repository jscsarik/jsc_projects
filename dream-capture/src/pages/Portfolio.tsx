import { motion } from 'motion/react';
import { Instagram } from 'lucide-react';

const portfolioItems = Array.from({ length: 11 }, (_, i) => ({
  id: i + 1,
  image: `/portfolio/photo${i + 1}.jpg`,
  title: `Photo ${i + 1}`, // Titles can be updated later if needed
}));

export default function Portfolio() {
  return (
    <section className="container mx-auto px-6 py-24 bg-[#F5F2EB]">
      <div className="mb-20 text-center space-y-4">
        <h2 className="text-3xl md:text-4xl font-serif font-normal text-[#3A3532]">포트폴리오</h2>
        <p className="text-[#8C7B75] text-xs tracking-[0.2em] uppercase font-light">Selected Works</p>
      </div>

      <div className="columns-2 md:columns-3 gap-4 space-y-4">
        {portfolioItems.map((item, index) => (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: index * 0.1 }}
            className="break-inside-avoid mb-4 overflow-hidden rounded-sm cursor-pointer"
          >
            <img
              src={item.image}
              alt={`서울 개인 화보 감성 스냅 이재호필름 포트폴리오 ${item.id}`}
              className="w-full h-auto object-cover hover:scale-105 transition-transform duration-500"
              referrerPolicy="no-referrer"
            />
          </motion.div>
        ))}
      </div>

      <div className="mt-24 border-t border-[#3A3532]/10 pt-16 text-center space-y-8">
        <p className="text-[#3A3532] font-serif text-lg tracking-wide">
          더 많은 이야기는 인스타그램에서 확인하세요.
        </p>
        
        <a 
          href="https://www.instagram.com/ljh__flim/" 
          target="_blank" 
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-3 px-10 py-4 bg-[#3A3532] text-[#F5F2EB] rounded-sm hover:bg-[#2A2522] transition-all duration-300 text-sm tracking-widest uppercase font-medium"
        >
          <Instagram size={18} strokeWidth={1.5} />
          <span>View More on Instagram</span>
        </a>
      </div>
    </section>
  );
}
