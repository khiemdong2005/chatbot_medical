import React, { Fragment, useEffect } from "react";
import {
  X,
  Plus,
  MapPin,
  Star,
  Check,
  Calendar,
  Phone,
  Clock,
  CheckSquare,
} from "lucide-react";

/**
 * Props for the slide‑over drawer.
 * - `isOpen`   : Control visibility.
 * - `onClose`  : Callback when the overlay or close button is pressed.
 * - `hospital` : Optional data object; if omitted a mock example is used.
 */
export interface HospitalDetailsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  hospital: Hospital;
}

/* ---------- Data types (you can replace with your real models) ---------- */
export interface Hospital {
  title: string;
  address: string;
  hours: string; // e.g. "07:30 - 17:00 (Thứ 2 - Thứ 7)"
  category: string;
  rating: number;
  reviewsCount: string;
  specialties: string[];
  imageUrl?: string;
  mapUrl?: string;
  type: string;
}

export interface Tag {
  label: string;
  /** Tailwind colour class for background (e.g. "bg-cyan-900") */
  bgClass: string;
  /** Tailwind colour class for text (e.g. "text-cyan-300") */
  textClass: string;
  /** Optional icon component */
  icon?: JSX.Element;
}

export interface Amenity {
  label: string;
  icon?: JSX.Element;
}

export interface Doctor {
  initials: string;
  name: string;
  rating: number; // 0‑5
  specialty: string;
  experience: string; // e.g. "18 năm kinh nghiệm"
  availableToday: boolean;
  avatarBg: string; // Tailwind bg colour for the circle
}

export interface Review {
  title: string; // e.g. "Cơ sở vật chất"
  score: number; // 0‑5
}

/* ---------- Mock data (used when no `hospital` prop is passed) ---------- */
/* --------------------- Component implementation --------------------- */
export const HospitalDetailsDrawer: React.FC<HospitalDetailsDrawerProps> = ({
  isOpen,
  onClose,
  hospital,
}) => {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [isOpen, onClose]);

  const stopPropagation = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <Fragment>
      {/* Overlay */}
      <div
        className={`fixed inset-0 bg-black/60 backdrop-blur-sm z-40 transition-opacity duration-300 ${isOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        onClick={onClose}
      />

      {/* Drawer */}
      <aside
        aria-modal="true"
        role="dialog"
        aria-label={`Thông tin ${hospital.title}`}
        className={`fixed inset-y-0 right-0 z-50 w-full sm:w-[min(440px,38vw)] bg-[#0b1326] border-l border-[#2d3a54] shadow-2xl flex flex-col h-full overflow-hidden transition-transform duration-300 ease-out ${isOpen ? "translate-x-0" : "translate-x-full pointer-events-none"}`}
        onClick={stopPropagation}
      >
        {/* Scrollable main content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* ---------- Header ---------- */}
          <header className="relative">
            {/* Close button */}
            <button
              onClick={onClose}
              className="absolute right-0 top-0 rounded-full bg-[#151e32] text-slate-400 p-2 hover:bg-[#1a233a]"
            >
              <X size={20} />
            </button>

            {/* Hero image placeholder */}
            <div className="flex items-center justify-center h-40 bg-[#151e32] rounded-xl mb-4">
              {hospital.imageUrl ? <img src={hospital.imageUrl} alt={`Ảnh ${hospital.title}`} className="w-full h-full object-cover rounded-xl" /> : <div className="flex flex-col items-center gap-2 text-slate-500"><Plus size={40} /><span className="text-xs">Hình ảnh bệnh viện</span></div>}
            </div>

            {/* Tags row */}
            <div className="flex flex-wrap gap-2 mb-4">
              {[{ label: hospital.type, bgClass: "bg-cyan-900", textClass: "text-cyan-300" }, { label: hospital.category, bgClass: "bg-blue-900", textClass: "text-blue-300" }, { label: `${hospital.rating} (${hospital.reviewsCount})`, bgClass: "bg-amber-900", textClass: "text-amber-300", icon: <Star size={14} className="inline-block" /> }].map((tag, i) => (
                <span
                  key={i}
                  className={`inline-flex items-center gap-1 px-3 py-1 rounded-full ${tag.bgClass} ${tag.textClass} text-sm`}
                >
                  {tag.icon}
                  {tag.label}
                </span>
              ))}
            </div>

            {/* Title */}
            <h2 className="text-2xl font-bold text-white mb-2">
              {hospital.title}
            </h2>

            {/* Address */}
            <p className="flex items-center gap-2 text-slate-300 text-sm mb-2">
              <MapPin size={16} />
              {hospital.address}
            </p>

            {/* Time & status pills */}
            <div className="flex flex-wrap gap-2">
              <span className="px-3 py-1 bg-[#151e32] text-slate-400 rounded-full text-sm flex items-center gap-1">
                <Clock size={14} />
                {hospital.hours}
              </span>
              <span className="px-3 py-1 bg-[#151e32] text-green-300 rounded-full text-sm flex items-center gap-1">
                <CheckSquare size={14} className="text-green-400" />
                Cấp cứu 24/7
              </span>
            </div>
          </header>

          {/* ---------- Amenities ---------- */}
          <section>
            <h3 className="text-xs uppercase text-slate-400 mb-3">CHUYÊN KHOA & DỊCH VỤ</h3>
            <div className="flex flex-wrap gap-2">
              {hospital.specialties.map((specialty, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-[#151e32] text-slate-300 rounded-lg text-sm"
                >
                  {specialty}
                </span>
              ))}
            </div>
          </section>

          {/* ---------- Featured Doctors ---------- */}
          <section>
            <div className="flex justify-between items-center mb-3">
              <h3 className="flex items-center gap-2 text-sm font-medium text-white">
                <Check size={16} className="text-cyan-400" />
                Thông tin cơ sở
              </h3>
            </div>

            <div className="space-y-3">
              {[
                { initials: hospital.title.slice(0, 2), name: hospital.title, specialty: hospital.type, experience: hospital.address, rating: hospital.rating, availableToday: true, avatarBg: "bg-cyan-700" },
                ...hospital.specialties.slice(0, 2).map((specialty, index) => ({ initials: "✚", name: specialty, specialty: "Chuyên khoa tiếp nhận", experience: hospital.hours, rating: hospital.rating, availableToday: true, avatarBg: index ? "bg-teal-700" : "bg-blue-700" })),
              ].map((doc, i) => (
                <div
                  key={i}
                  className="flex gap-3 bg-[#151e32] rounded-2xl p-3"
                >
                  {/* Avatar */}
                  <div
                    className={`flex items-center justify-center w-12 h-12 rounded-full ${doc.avatarBg} text-white text-lg font-medium`}
                  >
                    {doc.initials}
                  </div>

                  {/* Info */}
                  <div className="flex-1">
                    <div className="flex items-center gap-1 text-white text-sm font-medium">
                      {doc.name}
                      <Star size={14} className="text-yellow-400" />
                      <span className="text-yellow-300">{doc.rating}</span>
                    </div>
                    <p className="text-cyan-300 text-xs">{doc.specialty}</p>
                    <div className="flex items-center gap-1 text-slate-400 text-xs mt-1">
                      <span>{doc.experience}</span>
                      {doc.availableToday && (
                        <span className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-green-500 rounded-full" />
                          Có lịch hôm nay
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ---------- Patient Reviews ---------- */}
          <section>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-medium text-white">
                Đánh giá từ bệnh nhân đã khám
              </h3>
              <span className="text-slate-400 text-sm">
                1,428 phản hồi xác thực
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {hospital.specialties.slice(0, 3).map((specialty, i) => (
                <div
                  key={i}
                  className="bg-[#151e32] rounded-xl p-4 text-center"
                >
                  <p className="text-slate-300 text-xs mb-1">{specialty}</p>
                  <div className="flex items-center justify-center gap-1 text-yellow-400">
                    <Star size={16} />
                    <span className="text-white font-medium">{hospital.rating}</span>
                    <span className="text-slate-400">/5</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* ---------- Sticky Footer ---------- */}
        <footer className="bg-[#0b1326] p-4 border-t border-[#2d3a54]">
          {/* Primary action */}
          <button className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl py-2.5 font-semibold transition-colors">
            <Calendar size={18} />
            Đặt lịch khám ngay
          </button>

          {/* Secondary actions */}
          <div className="flex gap-2 mt-2">
            <button className="flex-1 flex items-center justify-center gap-1 bg-[#151e32] hover:bg-[#1a233a] text-slate-400 rounded-lg py-2.5 transition-colors">
              <Phone size={16} />
              {hospital.hours.split(" • ")[0]}
            </button>
            <button className="flex-1 flex items-center justify-center gap-1 bg-[#151e32] hover:bg-[#1a233a] text-slate-400 rounded-lg py-2.5 transition-colors">
              <MapPin size={16} />
              <a href={hospital.mapUrl || "https://maps.google.com"} target="_blank" rel="noreferrer">Chỉ đường Maps</a>
            </button>
          </div>
        </footer>
      </aside>
    </Fragment>
  );
};

export default HospitalDetailsDrawer;
