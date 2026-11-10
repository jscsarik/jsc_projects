import { motion } from 'motion/react';
import { Check } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Pricing() {
  return (
    <section className="container mx-auto px-6 py-24 bg-[#F5F2EB]">
      <div className="mb-20 text-center space-y-4">
        <h2 className="text-3xl md:text-4xl font-serif font-normal text-[#3A3532]">가격 안내</h2>
        <p className="text-[#8C7B75] text-xs tracking-[0.2em] uppercase font-light">Pricing</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto mb-16">
        {/* BASIC Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="bg-[#FDFBF7] border border-[#3A3532]/10 p-10 rounded-sm flex flex-col items-center text-center hover:shadow-sm transition-shadow duration-300"
        >
          <h3 className="text-xl font-serif font-medium text-[#3A3532] mb-2">BASIC 스냅</h3>
          <div className="text-3xl font-light text-[#3A3532] mb-8 tracking-tight">
            40,000 <span className="text-base font-normal text-[#8C7B75]">KRW</span>
          </div>
          
          <ul className="space-y-4 w-full mb-10">
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>30분 촬영</span>
            </li>
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>정밀 보정본 6장 제공</span>
            </li>
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>셀렉용 원본 파일 전체 제공</span>
            </li>
          </ul>

          <Link to="/reservation" className="w-full py-4 border border-[#3A3532]/20 text-[#3A3532] text-xs tracking-widest uppercase hover:bg-[#3A3532] hover:text-[#F5F2EB] transition-colors duration-300 block">
            예약하기
          </Link>
        </motion.div>

        {/* STANDARD Card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="bg-[#FDFBF7] border border-[#3A3532]/10 p-10 rounded-sm flex flex-col items-center text-center hover:shadow-sm transition-shadow duration-300 relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 bg-[#8C7B75] text-[#F5F2EB] text-[10px] px-3 py-1 tracking-widest uppercase">
            Best
          </div>
          
          <h3 className="text-xl font-serif font-medium text-[#3A3532] mb-2">STANDARD 스냅</h3>
          <div className="text-3xl font-light text-[#3A3532] mb-8 tracking-tight">
            60,000 <span className="text-base font-normal text-[#8C7B75]">KRW</span>
          </div>
          
          <ul className="space-y-4 w-full mb-10">
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>1시간 촬영</span>
            </li>
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>정밀 보정본 8장 + 색감 보정본 5장 제공</span>
            </li>
            <li className="flex items-center justify-center gap-3 text-[#5D5D5D] font-light text-sm">
              <Check size={16} className="text-[#8C7B75]" />
              <span>셀렉용 원본 파일 전체 제공</span>
            </li>
          </ul>

          <Link to="/reservation" className="w-full py-4 bg-[#3A3532] text-[#F5F2EB] text-xs tracking-widest uppercase hover:bg-[#2A2522] transition-colors duration-300 block">
            예약하기
          </Link>
        </motion.div>
      </div>

      <div className="max-w-2xl mx-auto text-center space-y-2">
        <p className="text-[#8C7B75]/80 text-xs font-light tracking-wide">
          * 원활한 스케줄 관리를 위해 예약금 10,000원을 입금해 주시면 예약이 최종 확정됩니다. 잔금은 촬영 당일 결제 부탁드립니다.
        </p>
        <p className="text-[#8C7B75]/80 text-xs font-light tracking-wide">
          * 수도권 촬영 시 작가 교통비는 가격에 포함됩니다 (수도권 외 지역 미포함)
        </p>
      </div>
    </section>
  );
}
