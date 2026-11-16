import React, { useState } from 'react';
import { HospitalDetailsDrawer, type Hospital as DrawerHospital } from './HospitalDetailsDrawer';
import {
  Search,
  MapPin,
  Clock,
  Star,
  Building2,
  Map,
  ChevronDown,
  Navigation,
  Calendar,
  Sparkles,
  Stethoscope,
  Globe2,
  FlaskConical,
  CheckCircle2,
} from 'lucide-react';

export interface Hospital {
  id: string;
  name: string;
  type: string;
  typeBadgeColor: string;
  rating: number;
  reviewsCount: string;
  address: string;
  distance: string;
  specialties: string[];
  workingHours: string;
  category: 'general' | 'international' | 'specialized' | 'lab';
  region: 'hcm' | 'hn' | 'dn';
  mapUrl?: string;
}

const mockHospitals: Hospital[] = [
  {
    id: '1',
    name: 'Bệnh viện Đại học Y Dược TP.HCM',
    type: 'Tuyến Trung Ương',
    typeBadgeColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    rating: 4.8,
    reviewsCount: '2.8k',
    address: '215 Hồng Bàng, Phường 11, Quận 5',
    distance: '~ 2.8 km',
    specialties: ['Tiêu hóa & Gan', 'Nội tiết', 'Hô hấp', 'BHYT'],
    workingHours: '06:30 - 16:30 • Có khám theo yêu cầu',
    category: 'general',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Bệnh+viện+Đại+học+Y+Dược+TPHCM',
  },
  {
    id: '2',
    name: 'BVĐK Quốc Tế Vinmec Central Park',
    type: 'Chuẩn JCI Quốc Tế',
    typeBadgeColor: 'text-sky-400 bg-sky-500/10 border-sky-500/20',
    rating: 4.9,
    reviewsCount: '1.4k',
    address: '208 Nguyễn Hữu Cảnh, Q. Bình Thạnh',
    distance: '~ 3.2 km',
    specialties: ['Tim mạch', 'Ung bướu', 'Sản phụ khoa', 'Nhi'],
    workingHours: '07:30 - 17:00 • Cấp cứu 24/7',
    category: 'general',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Vinmec+Central+Park',
  },
  {
    id: '3',
    name: 'Bệnh viện Chợ Rẫy',
    type: 'Hạng Đặc Biệt',
    typeBadgeColor: 'text-rose-400 bg-rose-500/10 border-rose-500/20',
    rating: 4.7,
    reviewsCount: '3.5k',
    address: '201B Nguyễn Chí Thanh, Quận 5',
    distance: '~ 3.5 km',
    specialties: ['Cấp cứu hồi sức', 'Ghép tạng', 'Ngoại thần kinh', 'BHYT'],
    workingHours: '07:00 - 16:00 • Trực cấp cứu 24/24',
    category: 'general',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Bệnh+viện+Chợ+Rẫy',
  },
  {
    id: '4',
    name: 'Bệnh viện Tai Mũi Họng TP.HCM',
    type: 'Chuyên Khoa Sâu',
    typeBadgeColor: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    rating: 4.6,
    reviewsCount: '1.8k',
    address: '410 Lê Văn Sỹ, Phường 14, Quận 3',
    distance: '~ 1.4 km',
    specialties: ['Tai Mũi Họng', 'Phẫu thuật đầu cổ', 'Thính học', 'BHYT'],
    workingHours: '07:00 - 16:30 • Khám ngoài giờ',
    category: 'specialized',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Bệnh+viện+Tai+Mũi+Họng+TPHCM',
  },
  {
    id: '5',
    name: 'Phòng khám Quốc tế Raffles Medical',
    type: 'Bảo Hiểm Quốc Tế',
    typeBadgeColor: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    rating: 4.9,
    reviewsCount: '840',
    address: '167A Nam Kỳ Khởi Nghĩa, Quận 3',
    distance: '~ 1.8 km',
    specialties: ['Đa khoa', 'Bác sĩ Pháp - Sing', 'Tiêm chủng', 'Xét nghiệm'],
    workingHours: '08:00 - 20:00 • Tiếp nhận nhanh',
    category: 'international',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Raffles+Medical+HCMC',
  },
  {
    id: '6',
    name: 'Viện Tim TP. Hồ Chí Minh',
    type: 'Chuyên Khoa Tim Mạch',
    typeBadgeColor: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    rating: 4.8,
    reviewsCount: '1.1k',
    address: '04 Dương Quang Trung, Quận 10',
    distance: '~ 3.6 km',
    specialties: ['Tim mạch', 'Can thiệp tim mạch', 'Phẫu thuật lồng ngực'],
    workingHours: '07:00 - 16:30 • Đặt lịch trực tuyến',
    category: 'specialized',
    region: 'hcm',
    mapUrl: 'https://maps.google.com/?q=Viện+Tim+TPHCM',
  },
];

export const MedicalDirectory: React.FC = () => {
  const [searchSidebar, setSearchSidebar] = useState('');
  const [searchMain, setSearchMain] = useState('');
  const [selectedFacilityType, setSelectedFacilityType] = useState('all');
  const [selectedRegion, setSelectedRegion] = useState('hcm');
  const [selectedSpecialties, setSelectedSpecialties] = useState<string[]>(['Tim mạch']);
  const [selectedHospital, setSelectedHospital] = useState<Hospital | null>(null);

  const toDrawerHospital = (hospital: Hospital): DrawerHospital => ({
    title: hospital.name,
    address: hospital.address,
    hours: hospital.workingHours,
    category: hospital.category === 'international' ? 'Phòng khám quốc tế' : hospital.category === 'specialized' ? 'Bệnh viện chuyên khoa' : 'Bệnh viện đa khoa',
    type: hospital.type,
    rating: hospital.rating,
    reviewsCount: hospital.reviewsCount,
    specialties: hospital.specialties,
    mapUrl: hospital.mapUrl,
  });

  const facilityCategories = [
    { id: 'all', label: 'Tất cả cơ sở', count: 148, icon: Sparkles },
    { id: 'general', label: 'Bệnh viện Đa khoa', count: 52, icon: Building2 },
    { id: 'international', label: 'Phòng khám Quốc tế', count: 36, icon: Globe2 },
    { id: 'specialized', label: 'Bệnh viện Chuyên khoa', count: 41, icon: Stethoscope },
    { id: 'lab', label: 'Trung tâm Xét nghiệm', count: 19, icon: FlaskConical },
  ];

  const regions = [
    { id: 'hcm', label: 'TP. HCM' },
    { id: 'hn', label: 'Hà Nội' },
    { id: 'dn', label: 'Đà Nẵng' },
  ];

  const specialtyTags = [
    'Tim mạch',
    'Nhi khoa',
    'Tai Mũi Họng',
    'Nội tiết & Tiểu đường',
    'Tiêu hóa & Gan mật',
    'Chấn thương chỉnh hình',
    'Thần kinh',
    'Hô hấp',
    'Da liễu',
  ];

  const toggleSpecialty = (item: string) => {
    setSelectedSpecialties(prev =>
      prev.includes(item) ? prev.filter(s => s !== item) : [...prev, item]
    );
  };

  const filteredHospitals = mockHospitals.filter(hospital => {
    const query = (searchMain || searchSidebar).toLowerCase().trim();
    if (query) {
      const matchName = hospital.name.toLowerCase().includes(query);
      const matchAddress = hospital.address.toLowerCase().includes(query);
      const matchSpec = hospital.specialties.some(s => s.toLowerCase().includes(query));
      if (!matchName && !matchAddress && !matchSpec) return false;
    }
    if (selectedFacilityType !== 'all' && hospital.category !== selectedFacilityType) {
      return false;
    }
    if (selectedRegion && hospital.region !== selectedRegion) {
      return false;
    }
    return true;
  });

  return (
    <div className="min-h-screen bg-[#0b1326] text-slate-100 font-sans p-4 sm:p-6 lg:p-8 antialiased selection:bg-blue-600 selection:text-white">
      {/* 2-column layout container */}
      <div className="max-w-[1600px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        {/* ========================================================= */}
        {/* 1. LEFT SIDEBAR (lg:col-span-3)                          */}
        {/* ========================================================= */}
        <aside className="lg:col-span-3 flex flex-col gap-6 bg-[#151e32] p-5 rounded-2xl border border-[#2d3a54] shadow-xl">
          {/* Header */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
                <Building2 className="w-5 h-5 text-blue-500" />
                Cơ Sở Y Tế
              </h2>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-medium">
                148 Cơ sở
              </span>
            </div>

            {/* Search Input Sidebar */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                value={searchSidebar}
                onChange={(e) => setSearchSidebar(e.target.value)}
                placeholder="Tìm bệnh viện, phòng khám..."
                className="w-full pl-9 pr-3 py-2 text-xs bg-[#0b1326] border border-[#2d3a54] rounded-xl text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
              />
            </div>
          </div>

          {/* Section 1: LOẠI HÌNH CƠ SỞ */}
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2.5">
              Loại hình cơ sở
            </span>
            <div className="space-y-1">
              {facilityCategories.map((cat) => {
                const Icon = cat.icon;
                const isActive = selectedFacilityType === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setSelectedFacilityType(cat.id)}
                    className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-150 ${
                      isActive
                        ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30 font-semibold shadow-sm'
                        : 'text-slate-300 hover:text-white hover:bg-[#1a233a] border border-transparent'
                    }`}
                  >
                    <span className="flex items-center gap-2.5">
                      <Icon className={`w-4 h-4 ${isActive ? 'text-blue-400' : 'text-slate-400'}`} />
                      {cat.label}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-mono ${
                        isActive
                          ? 'bg-blue-600/30 text-blue-300'
                          : 'bg-[#0b1326] text-slate-400 border border-[#2d3a54]'
                      }`}
                    >
                      {cat.count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 2: KHU VỰC ĐỊA LÝ */}
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2.5">
              Khu vực địa lý
            </span>
            <div className="grid grid-cols-3 gap-2">
              {regions.map((region) => {
                const isActive = selectedRegion === region.id;
                return (
                  <button
                    key={region.id}
                    onClick={() => setSelectedRegion(region.id as 'hcm' | 'hn' | 'dn')}
                    className={`py-2 px-2.5 rounded-full text-xs font-semibold transition-all text-center ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                        : 'bg-[#0b1326] hover:bg-[#1a233a] text-slate-300 hover:text-white border border-[#2d3a54]'
                    }`}
                  >
                    {region.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 3: CHUYÊN KHOA NỔI BẬT */}
          <div>
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2.5">
              Chuyên khoa nổi bật
            </span>
            <div className="flex flex-wrap gap-1.5">
              {specialtyTags.map((spec) => {
                const isSelected = selectedSpecialties.includes(spec);
                return (
                  <button
                    key={spec}
                    onClick={() => toggleSpecialty(spec)}
                    className={`px-3 py-1.5 rounded-full text-[11px] font-medium transition-all ${
                      isSelected
                        ? 'bg-blue-600/25 text-blue-300 border border-blue-500/40 shadow-sm'
                        : 'bg-[#0b1326] text-slate-400 hover:text-slate-200 border border-[#2d3a54] hover:border-slate-500'
                    }`}
                  >
                    {spec}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Footer note */}
          <div className="pt-4 border-t border-[#2d3a54] flex items-center justify-between text-[11px] text-slate-400">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />
              Bảo mật đặt hẹn
            </span>
            <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Kết nối BV 24/7
            </span>
          </div>
        </aside>

        {/* ========================================================= */}
        {/* 2. RIGHT MAIN AREA (lg:col-span-9)                       */}
        {/* ========================================================= */}
        <main className="lg:col-span-9 flex flex-col gap-5">
          {/* Top Bar */}
          <div className="p-4 rounded-2xl bg-[#151e32] border border-[#2d3a54] shadow-xl flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-blue-400 absolute left-3.5 top-3.5" />
              <input
                type="text"
                value={searchMain}
                onChange={(e) => setSearchMain(e.target.value)}
                placeholder="Nhập tên bệnh viện, triệu chứng, bác sĩ chuyên khoa..."
                className="w-full pl-10 pr-4 py-2.5 text-xs bg-[#0b1326] border border-[#2d3a54] rounded-full text-slate-100 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner"
              />
            </div>

            <div className="flex items-center gap-2.5 self-end sm:self-auto shrink-0">
              <button className="px-4 py-2.5 text-xs bg-[#0b1326] border border-[#2d3a54] hover:border-slate-500 text-slate-200 rounded-full flex items-center gap-2 transition-all">
                <span>Tất cả quận/huyện (TP.HCM)</span>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              <a
                href="https://maps.google.com"
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2.5 text-xs font-semibold text-white bg-[#0b1326] hover:bg-[#1a233a] border border-[#2d3a54] hover:border-blue-500 rounded-full flex items-center gap-2 transition-all shadow-sm"
              >
                <Map className="w-3.5 h-3.5 text-blue-400" />
                <span>Bản đồ</span>
              </a>
            </div>
          </div>

          {/* Meta Info Bar */}
          <div className="px-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
            <div className="text-slate-300 font-medium flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              <span>
                Hiển thị <strong className="text-white font-bold">{filteredHospitals.length}</strong> cơ sở y tế uy tín đạt chuẩn Bộ Y tế & MedlinePlus
              </span>
            </div>
            <div className="text-slate-400 text-[11px] flex items-center gap-1">
              <span>Sắp xếp:</span>
              <strong className="text-slate-200 font-semibold cursor-pointer hover:underline">
                Gần nhất & Đánh giá cao
              </strong>
            </div>
          </div>

          {/* Hospital Cards Grid (2 columns: xl:grid-cols-2) */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            {filteredHospitals.map((hospital) => (
              <div
                key={hospital.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelectedHospital(hospital)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    setSelectedHospital(hospital);
                  }
                }}
                className="cursor-pointer bg-[#151e32] rounded-2xl p-5 border border-[#2d3a54] hover:border-blue-500/60 transition-all duration-200 hover:shadow-xl hover:shadow-blue-500/5 flex flex-col justify-between group"
              >
                <div>
                  {/* Top row */}
                  <div className="flex items-start gap-3.5 mb-3.5">
                    <div className="w-12 h-12 rounded-xl bg-[#0b1326] border border-[#2d3a54] group-hover:border-blue-500/40 flex items-center justify-center shrink-0 text-blue-400 transition-colors shadow-inner">
                      <Building2 className="w-6 h-6 stroke-[1.8]" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] font-bold flex items-center gap-1">
                          <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                          {hospital.rating} <span className="text-slate-400 font-normal">({hospital.reviewsCount})</span>
                        </span>

                        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${hospital.typeBadgeColor}`}>
                          {hospital.type}
                        </span>
                      </div>

                      <h3 className="text-base font-bold text-white group-hover:text-blue-400 transition-colors truncate">
                        {hospital.name}
                      </h3>
                    </div>
                  </div>

                  {/* Address */}
                  <p className="text-xs text-slate-300 flex items-center gap-1.5 mb-3">
                    <MapPin className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span className="truncate">{hospital.address}</span>
                    <span className="text-blue-400 font-semibold shrink-0">• {hospital.distance}</span>
                  </p>

                  {/* Specialties */}
                  <div className="flex flex-wrap gap-1.5 mb-3.5">
                    {hospital.specialties.map((spec, i) => (
                      <span
                        key={i}
                        className="text-[11px] px-2.5 py-1 rounded-lg bg-[#0b1326] text-slate-300 border border-[#2d3a54] font-medium"
                      >
                        {spec}
                      </span>
                    ))}
                  </div>

                  {/* Working hours */}
                  <div className="text-[11px] text-emerald-400 flex items-center gap-2 mb-4 font-medium">
                    <Clock className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{hospital.workingHours}</span>
                  </div>
                </div>

                {/* Bottom Actions */}
                <div className="pt-3.5 border-t border-[#2d3a54] flex items-center gap-3">
                  <button
                    type="button"
                    className="flex-1 py-2.5 px-4 rounded-full bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all shadow-md shadow-blue-600/25 hover:shadow-blue-600/40 transform active:scale-95 flex items-center justify-center gap-1.5"
                  >
                    <Calendar className="w-3.5 h-3.5" />
                    <span>Đặt lịch khám</span>
                  </button>

                  <a
                    href={hospital.mapUrl || 'https://maps.google.com'}
                    onClick={(event) => event.stopPropagation()}
                    target="_blank"
                    rel="noreferrer"
                    className="py-2.5 px-4 rounded-full bg-[#0b1326] hover:bg-[#1a233a] border border-[#2d3a54] hover:border-slate-400 text-slate-200 text-xs font-semibold transition-all flex items-center justify-center gap-1.5"
                  >
                    <Navigation className="w-3.5 h-3.5 text-blue-400" />
                    <span>Chỉ đường</span>
                  </a>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
      <HospitalDetailsDrawer
        isOpen={selectedHospital !== null}
        onClose={() => setSelectedHospital(null)}
        hospital={selectedHospital ? toDrawerHospital(selectedHospital) : toDrawerHospital(mockHospitals[0])}
      />
    </div>
  );
};

export default MedicalDirectory;
