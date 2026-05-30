import { useState, useMemo } from "react";
import { Calculator, Search, X, Beaker, ChevronDown, ArrowLeft, ArrowLeftRight, Droplets, FlaskConical } from "lucide-react";
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from "recharts";

// ═══════════════════════════════════════════════════════════
// Periodic Table Data
// ═══════════════════════════════════════════════════════════

interface ElementData {
  z: number;
  symbol: string;
  name: string;
  mass: number;
  config: string;
  eneg: number | null;
  oxStates: string;
  category: string;
  mp: number | null;
  bp: number | null;
}

const ELEMENTS: ElementData[] = [
  { z:1,  symbol:"H",  name:"氢",   mass:1.008,   config:"1s¹",           eneg:2.20, oxStates:"-1, +1",      category:"非金属",   mp:-259.16, bp:-252.88 },
  { z:2,  symbol:"He", name:"氦",   mass:4.0026,  config:"1s²",           eneg:null, oxStates:"0",          category:"稀有气体", mp:null,     bp:-268.93 },
  { z:3,  symbol:"Li", name:"锂",   mass:6.94,    config:"[He]2s¹",       eneg:0.98, oxStates:"+1",         category:"碱金属",   mp:180.5,   bp:1330 },
  { z:4,  symbol:"Be", name:"铍",   mass:9.0122,  config:"[He]2s²",       eneg:1.57, oxStates:"+2",         category:"碱土金属", mp:1287,    bp:2469 },
  { z:5,  symbol:"B",  name:"硼",   mass:10.81,   config:"[He]2s²2p¹",    eneg:2.04, oxStates:"+3",         category:"非金属",   mp:2076,    bp:3927 },
  { z:6,  symbol:"C",  name:"碳",   mass:12.011,  config:"[He]2s²2p²",    eneg:2.55, oxStates:"-4, -3, -2, -1, +1, +2, +3, +4", category:"非金属", mp:3550, bp:4027 },
  { z:7,  symbol:"N",  name:"氮",   mass:14.007,  config:"[He]2s²2p³",    eneg:3.04, oxStates:"-3, -2, -1, +1, +2, +3, +4, +5", category:"非金属", mp:-210.0, bp:-195.8 },
  { z:8,  symbol:"O",  name:"氧",   mass:15.999,  config:"[He]2s²2p⁴",    eneg:3.44, oxStates:"-2, -1, +1, +2", category:"非金属", mp:-218.8, bp:-183.0 },
  { z:9,  symbol:"F",  name:"氟",   mass:18.998,  config:"[He]2s²2p⁵",    eneg:3.98, oxStates:"-1",         category:"卤素",     mp:-219.67, bp:-188.11 },
  { z:10, symbol:"Ne", name:"氖",   mass:20.180,  config:"[He]2s²2p⁶",    eneg:null, oxStates:"0",          category:"稀有气体", mp:-248.59, bp:-246.05 },
  { z:11, symbol:"Na", name:"钠",   mass:22.990,  config:"[Ne]3s¹",       eneg:0.93, oxStates:"+1",         category:"碱金属",   mp:97.79,   bp:882.94 },
  { z:12, symbol:"Mg", name:"镁",   mass:24.305,  config:"[Ne]3s²",       eneg:1.31, oxStates:"+2",         category:"碱土金属", mp:650,     bp:1090 },
  { z:13, symbol:"Al", name:"铝",   mass:26.982,  config:"[Ne]3s²3p¹",    eneg:1.61, oxStates:"+3",         category:"金属",     mp:660.32,  bp:2519 },
  { z:14, symbol:"Si", name:"硅",   mass:28.085,  config:"[Ne]3s²3p²",    eneg:1.90, oxStates:"-4, +2, +4", category:"非金属",   mp:1414,    bp:3265 },
  { z:15, symbol:"P",  name:"磷",   mass:30.974,  config:"[Ne]3s²3p³",    eneg:2.19, oxStates:"-3, +3, +5", category:"非金属",   mp:44.15,   bp:280.5 },
  { z:16, symbol:"S",  name:"硫",   mass:32.06,   config:"[Ne]3s²3p⁴",    eneg:2.58, oxStates:"-2, +2, +4, +6", category:"非金属", mp:115.21, bp:444.61 },
  { z:17, symbol:"Cl", name:"氯",   mass:35.45,   config:"[Ne]3s²3p⁵",    eneg:3.16, oxStates:"-1, +1, +3, +5, +7", category:"卤素", mp:-101.5, bp:-34.04 },
  { z:18, symbol:"Ar", name:"氩",   mass:39.95,   config:"[Ne]3s²3p⁶",    eneg:null, oxStates:"0",          category:"稀有气体", mp:-189.34, bp:-185.85 },
  { z:19, symbol:"K",  name:"钾",   mass:39.098,  config:"[Ar]4s¹",       eneg:0.82, oxStates:"+1",         category:"碱金属",   mp:63.5,    bp:759 },
  { z:20, symbol:"Ca", name:"钙",   mass:40.08,   config:"[Ar]4s²",       eneg:1.00, oxStates:"+2",         category:"碱土金属", mp:842,     bp:1484 },
  { z:21, symbol:"Sc", name:"钪",   mass:44.956,  config:"[Ar]3d¹4s²",    eneg:1.36, oxStates:"+3",         category:"过渡金属", mp:1541,    bp:2836 },
  { z:22, symbol:"Ti", name:"钛",   mass:47.867,  config:"[Ar]3d²4s²",    eneg:1.54, oxStates:"+2, +3, +4", category:"过渡金属", mp:1668,    bp:3287 },
  { z:23, symbol:"V",  name:"钒",   mass:50.942,  config:"[Ar]3d³4s²",    eneg:1.63, oxStates:"+2, +3, +4, +5", category:"过渡金属", mp:1910, bp:3407 },
  { z:24, symbol:"Cr", name:"铬",   mass:51.996,  config:"[Ar]3d⁵4s¹",    eneg:1.66, oxStates:"+2, +3, +6", category:"过渡金属", mp:1907, bp:2671 },
  { z:25, symbol:"Mn", name:"锰",   mass:54.938,  config:"[Ar]3d⁵4s²",    eneg:1.55, oxStates:"+2, +3, +4, +6, +7", category:"过渡金属", mp:1246, bp:2061 },
  { z:26, symbol:"Fe", name:"铁",   mass:55.845,  config:"[Ar]3d⁶4s²",    eneg:1.83, oxStates:"+2, +3",     category:"过渡金属", mp:1538,    bp:2861 },
  { z:27, symbol:"Co", name:"钴",   mass:58.933,  config:"[Ar]3d⁷4s²",    eneg:1.88, oxStates:"+2, +3",     category:"过渡金属", mp:1495,    bp:2927 },
  { z:28, symbol:"Ni", name:"镍",   mass:58.693,  config:"[Ar]3d⁸4s²",    eneg:1.91, oxStates:"+2",         category:"过渡金属", mp:1455,    bp:2913 },
  { z:29, symbol:"Cu", name:"铜",   mass:63.546,  config:"[Ar]3d¹⁰4s¹",   eneg:1.90, oxStates:"+1, +2",     category:"过渡金属", mp:1084.62, bp:2562 },
  { z:30, symbol:"Zn", name:"锌",   mass:65.38,   config:"[Ar]3d¹⁰4s²",   eneg:1.65, oxStates:"+2",         category:"过渡金属", mp:419.53,  bp:907 },
  { z:31, symbol:"Ga", name:"镓",   mass:69.723,  config:"[Ar]3d¹⁰4s²4p¹",eneg:1.81, oxStates:"+3",         category:"金属",     mp:29.76,   bp:2204 },
  { z:32, symbol:"Ge", name:"锗",   mass:72.63,   config:"[Ar]3d¹⁰4s²4p²",eneg:2.01, oxStates:"-4, +2, +4", category:"非金属",   mp:938.25,  bp:2833 },
  { z:33, symbol:"As", name:"砷",   mass:74.922,  config:"[Ar]3d¹⁰4s²4p³",eneg:2.18, oxStates:"-3, +3, +5", category:"非金属",   mp:817,     bp:614 },
  { z:34, symbol:"Se", name:"硒",   mass:78.96,   config:"[Ar]3d¹⁰4s²4p⁴",eneg:2.55, oxStates:"-2, +4, +6", category:"非金属",   mp:221,     bp:685 },
  { z:35, symbol:"Br", name:"溴",   mass:79.904,  config:"[Ar]3d¹⁰4s²4p⁵",eneg:2.96, oxStates:"-1, +1, +3, +5, +7", category:"卤素", mp:-7.2, bp:58.8 },
  { z:36, symbol:"Kr", name:"氪",   mass:83.80,   config:"[Ar]3d¹⁰4s²4p⁶",eneg:3.00, oxStates:"0, +2",      category:"稀有气体", mp:-157.37, bp:-153.42 },
  { z:37, symbol:"Rb", name:"铷",   mass:85.468,  config:"[Kr]5s¹",       eneg:0.82, oxStates:"+1",         category:"碱金属",   mp:39.3,    bp:688 },
  { z:38, symbol:"Sr", name:"锶",   mass:87.62,   config:"[Kr]5s²",       eneg:0.95, oxStates:"+2",         category:"碱土金属", mp:777,     bp:1377 },
  { z:39, symbol:"Y",  name:"钇",   mass:88.906,  config:"[Kr]4d¹5s²",    eneg:1.22, oxStates:"+3",         category:"过渡金属", mp:1526,    bp:3345 },
  { z:40, symbol:"Zr", name:"锆",   mass:91.224,  config:"[Kr]4d²5s²",    eneg:1.33, oxStates:"+4",         category:"过渡金属", mp:1855,    bp:4377 },
  { z:41, symbol:"Nb", name:"铌",   mass:92.906,  config:"[Kr]4d⁴5s¹",    eneg:1.60, oxStates:"+3, +5",     category:"过渡金属", mp:2477,    bp:4744 },
  { z:42, symbol:"Mo", name:"钼",   mass:95.95,   config:"[Kr]4d⁵5s¹",    eneg:2.16, oxStates:"+2, +3, +4, +5, +6", category:"过渡金属", mp:2623, bp:4639 },
  { z:43, symbol:"Tc", name:"锝",   mass:98,      config:"[Kr]4d⁵5s²",    eneg:1.90, oxStates:"+4, +7",     category:"过渡金属", mp:2157,    bp:4265 },
  { z:44, symbol:"Ru", name:"钌",   mass:101.07,  config:"[Kr]4d⁷5s¹",    eneg:2.20, oxStates:"+3, +4",     category:"过渡金属", mp:2334,    bp:4150 },
  { z:45, symbol:"Rh", name:"铑",   mass:102.91,  config:"[Kr]4d⁸5s¹",    eneg:2.28, oxStates:"+3",         category:"过渡金属", mp:1964,    bp:3695 },
  { z:46, symbol:"Pd", name:"钯",   mass:106.42,  config:"[Kr]4d¹⁰",      eneg:2.20, oxStates:"+2, +4",     category:"过渡金属", mp:1555,    bp:2963 },
  { z:47, symbol:"Ag", name:"银",   mass:107.87,  config:"[Kr]4d¹⁰5s¹",   eneg:1.93, oxStates:"+1",         category:"过渡金属", mp:961.78,  bp:2162 },
  { z:48, symbol:"Cd", name:"镉",   mass:112.41,  config:"[Kr]4d¹⁰5s²",   eneg:1.69, oxStates:"+2",         category:"过渡金属", mp:321.07,  bp:767 },
  { z:49, symbol:"In", name:"铟",   mass:114.82,  config:"[Kr]4d¹⁰5s²5p¹",eneg:1.78, oxStates:"+3",         category:"金属",     mp:156.6,   bp:2072 },
  { z:50, symbol:"Sn", name:"锡",   mass:118.71,  config:"[Kr]4d¹⁰5s²5p²",eneg:1.96, oxStates:"-4, +2, +4", category:"金属",     mp:231.93,  bp:2602 },
  { z:51, symbol:"Sb", name:"锑",   mass:121.76,  config:"[Kr]4d¹⁰5s²5p³",eneg:2.05, oxStates:"-3, +3, +5", category:"非金属",   mp:630.63,  bp:1587 },
  { z:52, symbol:"Te", name:"碲",   mass:127.60,  config:"[Kr]4d¹⁰5s²5p⁴",eneg:2.10, oxStates:"-2, +4, +6", category:"非金属",   mp:449.51,  bp:988 },
  { z:53, symbol:"I",  name:"碘",   mass:126.90,  config:"[Kr]4d¹⁰5s²5p⁵",eneg:2.66, oxStates:"-1, +1, +3, +5, +7", category:"卤素", mp:113.7, bp:184.3 },
  { z:54, symbol:"Xe", name:"氙",   mass:131.29,  config:"[Kr]4d¹⁰5s²5p⁶",eneg:2.60, oxStates:"0, +2, +4, +6, +8", category:"稀有气体", mp:-111.75, bp:-108.1 },
  { z:55, symbol:"Cs", name:"铯",   mass:132.91,  config:"[Xe]6s¹",       eneg:0.79, oxStates:"+1",         category:"碱金属",   mp:28.5,    bp:671 },
  { z:56, symbol:"Ba", name:"钡",   mass:137.33,  config:"[Xe]6s²",       eneg:0.89, oxStates:"+2",         category:"碱土金属", mp:727,     bp:1897 },
  { z:57, symbol:"La", name:"镧",   mass:138.91,  config:"[Xe]5d¹6s²",    eneg:1.10, oxStates:"+3",         category:"镧系",     mp:920,     bp:3464 },
  { z:58, symbol:"Ce", name:"铈",   mass:140.12,  config:"[Xe]4f¹5d¹6s²", eneg:1.12, oxStates:"+3, +4",     category:"镧系",     mp:795,     bp:3443 },
  { z:59, symbol:"Pr", name:"镨",   mass:140.91,  config:"[Xe]4f³6s²",    eneg:1.13, oxStates:"+3",         category:"镧系",     mp:935,     bp:3520 },
  { z:60, symbol:"Nd", name:"钕",   mass:144.24,  config:"[Xe]4f⁴6s²",    eneg:1.14, oxStates:"+3",         category:"镧系",     mp:1024,    bp:3074 },
  { z:62, symbol:"Sm", name:"钐",   mass:150.36,  config:"[Xe]4f⁶6s²",    eneg:1.17, oxStates:"+2, +3",     category:"镧系",     mp:1072,    bp:1794 },
  { z:63, symbol:"Eu", name:"铕",   mass:151.96,  config:"[Xe]4f⁷6s²",    eneg:1.20, oxStates:"+2, +3",     category:"镧系",     mp:826,     bp:1529 },
  { z:64, symbol:"Gd", name:"钆",   mass:157.25,  config:"[Xe]4f⁷5d¹6s²", eneg:1.20, oxStates:"+3",         category:"镧系",     mp:1312,    bp:3273 },
  { z:65, symbol:"Tb", name:"铽",   mass:158.93,  config:"[Xe]4f⁹6s²",    eneg:1.20, oxStates:"+3",         category:"镧系",     mp:1356,    bp:3230 },
  { z:66, symbol:"Dy", name:"镝",   mass:162.50,  config:"[Xe]4f¹⁰6s²",   eneg:1.22, oxStates:"+3",         category:"镧系",     mp:1412,    bp:2567 },
  { z:67, symbol:"Ho", name:"钬",   mass:164.93,  config:"[Xe]4f¹¹6s²",   eneg:1.23, oxStates:"+3",         category:"镧系",     mp:1474,    bp:2700 },
  { z:68, symbol:"Er", name:"铒",   mass:167.26,  config:"[Xe]4f¹²6s²",   eneg:1.24, oxStates:"+3",         category:"镧系",     mp:1529,    bp:2868 },
  { z:69, symbol:"Tm", name:"铥",   mass:168.93,  config:"[Xe]4f¹³6s²",   eneg:1.25, oxStates:"+3",         category:"镧系",     mp:1545,    bp:1950 },
  { z:70, symbol:"Yb", name:"镱",   mass:173.04,  config:"[Xe]4f¹⁴6s²",   eneg:1.10, oxStates:"+2, +3",     category:"镧系",     mp:824,     bp:1196 },
  { z:71, symbol:"Lu", name:"镥",   mass:174.97,  config:"[Xe]4f¹⁴5d¹6s²",eneg:1.27, oxStates:"+3",         category:"镧系",     mp:1663,    bp:3402 },
  { z:72, symbol:"Hf", name:"铪",   mass:178.49,  config:"[Xe]4f¹⁴5d²6s²",eneg:1.30, oxStates:"+4",         category:"过渡金属", mp:2233,    bp:4603 },
  { z:73, symbol:"Ta", name:"钽",   mass:180.95,  config:"[Xe]4f¹⁴5d³6s²",eneg:1.50, oxStates:"+5",         category:"过渡金属", mp:3017,    bp:5458 },
  { z:74, symbol:"W",  name:"钨",   mass:183.84,  config:"[Xe]4f¹⁴5d⁴6s²",eneg:2.36, oxStates:"+2, +3, +4, +5, +6", category:"过渡金属", mp:3422, bp:5555 },
  { z:75, symbol:"Re", name:"铼",   mass:186.21,  config:"[Xe]4f¹⁴5d⁵6s²",eneg:1.90, oxStates:"+4, +7",     category:"过渡金属", mp:3186,    bp:5596 },
  { z:76, symbol:"Os", name:"锇",   mass:190.23,  config:"[Xe]4f¹⁴5d⁶6s²",eneg:2.20, oxStates:"+4, +6, +8", category:"过渡金属", mp:3033,    bp:5012 },
  { z:77, symbol:"Ir", name:"铱",   mass:192.22,  config:"[Xe]4f¹⁴5d⁷6s²",eneg:2.20, oxStates:"+3, +4",     category:"过渡金属", mp:2446,    bp:4428 },
  { z:78, symbol:"Pt", name:"铂",   mass:195.08,  config:"[Xe]4f¹⁴5d⁹6s¹",eneg:2.28, oxStates:"+2, +4",     category:"过渡金属", mp:1768.3,  bp:3825 },
  { z:79, symbol:"Au", name:"金",   mass:196.97,  config:"[Xe]4f¹⁴5d¹⁰6s¹",eneg:2.54, oxStates:"+1, +3",    category:"过渡金属", mp:1064.18, bp:2856 },
  { z:80, symbol:"Hg", name:"汞",   mass:200.59,  config:"[Xe]4f¹⁴5d¹⁰6s²",eneg:2.00, oxStates:"+1, +2",    category:"过渡金属", mp:-38.83,  bp:356.73 },
  { z:81, symbol:"Tl", name:"铊",   mass:204.38,  config:"[Xe]4f¹⁴5d¹⁰6s²6p¹",eneg:1.80, oxStates:"+1, +3",category:"金属",   mp:304,     bp:1473 },
  { z:82, symbol:"Pb", name:"铅",   mass:207.2,   config:"[Xe]4f¹⁴5d¹⁰6s²6p²",eneg:2.33, oxStates:"-4, +2, +4", category:"金属", mp:327.46, bp:1749 },
  { z:83, symbol:"Bi", name:"铋",   mass:208.98,  config:"[Xe]4f¹⁴5d¹⁰6s²6p³",eneg:2.02, oxStates:"+3",     category:"金属",     mp:271.4,   bp:1564 },
  { z:84, symbol:"Po", name:"钋",   mass:209,     config:"[Xe]4f¹⁴5d¹⁰6s²6p⁴",eneg:2.00, oxStates:"+2, +4",category:"非金属",   mp:254,     bp:962 },
  { z:86, symbol:"Rn", name:"氡",   mass:222,     config:"[Xe]4f¹⁴5d¹⁰6s²6p⁶",eneg:2.20, oxStates:"0",      category:"稀有气体", mp:-71,     bp:-61.7 },
  { z:87, symbol:"Fr", name:"钫",   mass:223,     config:"[Rn]7s¹",       eneg:0.70, oxStates:"+1",         category:"碱金属",   mp:27,      bp:677 },
  { z:88, symbol:"Ra", name:"镭",   mass:226,     config:"[Rn]7s²",       eneg:0.90, oxStates:"+2",         category:"碱土金属", mp:700,     bp:1737 },
  { z:90, symbol:"Th", name:"钍",   mass:232.04,  config:"[Rn]6d²7s²",    eneg:1.30, oxStates:"+4",         category:"锕系",     mp:1750,    bp:4788 },
  { z:92, symbol:"U",  name:"铀",   mass:238.03,  config:"[Rn]5f³6d¹7s²", eneg:1.38, oxStates:"+3, +4, +5, +6", category:"锕系", mp:1132.2, bp:4131 },
  { z:94, symbol:"Pu", name:"钚",   mass:244,     config:"[Rn]5f⁶7s²",    eneg:1.28, oxStates:"+3, +4, +5, +6", category:"锕系", mp:639.4, bp:3228 },
];

const ELEMENT_MAP = new Map<string, ElementData>();
ELEMENTS.forEach((el) => {
  ELEMENT_MAP.set(el.symbol, el);
  ELEMENT_MAP.set(el.symbol.toLowerCase(), el);
});

const ELEMENT_EN: Record<string, string> = {
  H:"Hydrogen", He:"Helium", Li:"Lithium", Be:"Beryllium", B:"Boron", C:"Carbon", N:"Nitrogen",
  O:"Oxygen", F:"Fluorine", Ne:"Neon", Na:"Sodium", Mg:"Magnesium", Al:"Aluminium",
  Si:"Silicon", P:"Phosphorus", S:"Sulfur", Cl:"Chlorine", Ar:"Argon", K:"Potassium",
  Ca:"Calcium", Sc:"Scandium", Ti:"Titanium", V:"Vanadium", Cr:"Chromium", Mn:"Manganese",
  Fe:"Iron", Co:"Cobalt", Ni:"Nickel", Cu:"Copper", Zn:"Zinc", Ga:"Gallium", Ge:"Germanium",
  As:"Arsenic", Se:"Selenium", Br:"Bromine", Kr:"Krypton", Rb:"Rubidium", Sr:"Strontium",
  Y:"Yttrium", Zr:"Zirconium", Nb:"Niobium", Mo:"Molybdenum", Tc:"Technetium",
  Ru:"Ruthenium", Rh:"Rhodium", Pd:"Palladium", Ag:"Silver", Cd:"Cadmium", In:"Indium",
  Sn:"Tin", Sb:"Antimony", Te:"Tellurium", I:"Iodine", Xe:"Xenon", Cs:"Caesium",
  Ba:"Barium", La:"Lanthanum", Ce:"Cerium", Pr:"Praseodymium", Nd:"Neodymium",
  Sm:"Samarium", Eu:"Europium", Gd:"Gadolinium", Tb:"Terbium", Dy:"Dysprosium",
  Ho:"Holmium", Er:"Erbium", Tm:"Thulium", Yb:"Ytterbium", Lu:"Lutetium",
  Hf:"Hafnium", Ta:"Tantalum", W:"Tungsten", Re:"Rhenium", Os:"Osmium", Ir:"Iridium",
  Pt:"Platinum", Au:"Gold", Hg:"Mercury", Tl:"Thallium", Pb:"Lead", Bi:"Bismuth",
  Po:"Polonium", Rn:"Radon", Fr:"Francium", Ra:"Radium", Th:"Thorium", U:"Uranium",
  Pu:"Plutonium",
};

const ELEMENT_USES: Record<string, string> = {
  H:"用于合成氨、燃料电池、石油加氢精制和火箭燃料。", He:"用于低温冷却（超导磁体）、潜水呼吸气和检漏气体。",
  Li:"用于锂离子电池、航空航天轻质合金和陶瓷添加剂。", Be:"用于航空航天结构材料、X射线窗口和中子减速剂。",
  B:"用于硼硅酸盐玻璃、阻燃剂和半导体掺杂剂。", C:"用于钢铁冶炼、电极材料、复合材料和钻石饰品。",
  N:"用于合成氨（化肥）、食品保鲜和电子工业保护气氛。", O:"用于医疗呼吸支持、钢铁冶炼和火箭推进剂。",
  F:"用于牙膏添加剂、含氟聚合物（特氟龙）和制冷剂。", Ne:"用于霓虹灯、激光器和低温制冷剂。",
  Na:"用于食盐、钠灯、冶金还原剂和化工原料。", Mg:"用于轻质合金（航空航天、汽车）和烟火材料。",
  Al:"用于建筑材料、铝箔包装和航空航天合金。", Si:"用于半导体芯片、太阳能电池、玻璃和水泥。",
  P:"用于化肥、火柴、洗涤剂和阻燃剂。", S:"用于硫酸生产、橡胶硫化和化肥。",
  Cl:"用于自来水消毒、塑料（PVC）生产和漂白剂。", Ar:"用于焊接保护气和半导体制造保护气氛。",
  K:"用于钾肥、玻璃制造和肥皂工业。", Ca:"用于建筑材料、骨骼健康和冶金脱硫。",
  Sc:"用于航空航天铝合金和高强度运动器材。", Ti:"用于航空航天结构材料、医用植入物和耐腐蚀设备。",
  V:"用于钢铁添加剂（钒钢）和钒电池储能。", Cr:"用于不锈钢、电镀和颜料。",
  Mn:"用于钢铁冶炼脱氧剂和电池正极材料。", Fe:"用于建筑结构材料、机械制造和交通工具。",
  Co:"用于电池正极材料、高温合金和磁性材料。", Ni:"用于不锈钢、镍氢电池和电镀。",
  Cu:"用于电线电缆、管道和电子线路板。", Zn:"用于镀锌防腐蚀、锌基合金和干电池。",
  Ga:"用于半导体（GaAs/GaN）、LED照明和高温温度计。", Ge:"用于光纤通讯、红外光学和半导体衬底。",
  As:"用于半导体掺杂剂和合金添加剂。", Se:"用于玻璃着色、光电元件和硒鼓。",
  Br:"用于阻燃剂、药品和摄影材料。", Kr:"用于荧光灯、高功率激光器和窗隔热层。",
  Rb:"用于原子钟、光电管和特种玻璃。", Sr:"用于红色烟花、陶瓷磁性和牙齿护理。",
  Y:"用于LED荧光粉（YAG）、超导材料和激光晶体。", Zr:"用于核反应堆包覆材料和耐腐蚀合金。",
  Nb:"用于超导材料、特种钢添加剂。", Mo:"用于高强度合金、润滑剂添加剂和催化剂。",
  Tc:"用于医疗放射性同位素（心肌显像）。", Ru:"用于电子元器件厚膜电阻和催化剂。",
  Rh:"用于汽车催化转化器、珠宝镀层和热电偶。", Pd:"用于催化转化器、氢储存和电子接头。",
  Ag:"用于珠宝首饰、电子浆料和感光材料。", Cd:"用于镍镉电池、颜料和镀层防腐。",
  In:"用于透明电极（ITO触摸屏）、半导体和低温焊料。", Sn:"用于焊料、马口铁包装和青铜合金。",
  Sb:"用于阻燃剂添加剂和铅酸电池。", Te:"用于热电材料、橡胶添加剂和蓝光光盘。",
  I:"用于消毒剂、碘盐和医药。", Xe:"用于闪光灯、汽车头灯、麻醉剂和离子推进器。",
  Cs:"用于原子钟（铯钟）和石油钻井液。", Ba:"用于白色颜料、钻井液和X射线造影剂。",
  La:"用于光学玻璃、储氢合金和催化剂。", Ce:"用于汽车催化净化器、玻璃抛光粉。",
  Pr:"用于磁铁合金、光纤放大器和陶瓷颜料。", Nd:"用于强力永磁体（NdFeB）和激光器。",
  Sm:"用于磁性材料（SmCo磁铁）和核反应堆控制棒。", Eu:"用于荧光粉（红色荧光）和中子吸收剂。",
  Gd:"用于MRI造影剂、磁致冷材料和控制棒。", Tb:"用于绿色荧光粉和磁致伸缩材料。",
  Dy:"用于磁致伸缩材料（Terfenol-D）和控制棒。", Ho:"用于激光器和光纤放大器。",
  Er:"用于光纤放大器（掺铒光纤）和激光美容。", Tm:"用于便携式X射线源和激光器。",
  Yb:"用于光纤放大器、合金添加剂和压力传感器。", Lu:"用于催化剂和石油裂化。",
  Hf:"用于核反应堆控制棒、高温合金和微电子栅极。", Ta:"用于耐腐蚀设备、高温合金和植入物。",
  W:"用于灯丝、硬质合金刀具和电极。", Re:"用于高温合金（喷气发动机）和催化剂。",
  Os:"用于硬质合金、钟表轴承和电接触点。", Ir:"用于高温坩埚、合金硬化和卫星推进器。",
  Pt:"用于催化转化器、珠宝首饰和抗癌药物。", Au:"用于珠宝首饰、电子连接器和金条储备。",
  Hg:"用于温度计、荧光灯和化学电极。", Tl:"用于电子器件、红外光学和超导材料。",
  Pb:"用于铅酸电池、辐射屏蔽材料和焊料。", Bi:"用于低熔点合金、化妆品和胃药。",
  Po:"用于核电池（航天器）和抗静电刷。", Rn:"用于癌症放疗和地震预测研究。",
  Fr:"用于基础科学研究和放射性示踪。", Ra:"用于癌症放疗（历史用途）和发光涂料。",
  Th:"用于核燃料研究和高温陶瓷。", U:"用于核电站核燃料、贫铀装甲。",
  Pu:"用于核燃料（快中子堆）和核武器。",
};

// ═══════════════════════════════════════════════════════════
// Molar Mass Parser
// ═══════════════════════════════════════════════════════════

interface ParsedGroup {
  elements: { el: ElementData; count: number }[];
}

function parseFormula(formula: string): { el: ElementData; count: number }[] | null {
  const s = formula.replace(/\s/g, "");
  if (!s) return null;
  let i = 0;
  const result = parseGroup(s);
  if (result === null || i < s.length) return null;
  return result.elements;

  function parseGroup(): ParsedGroup | null {
    const elements: { el: ElementData; count: number }[] = [];
    while (i < s.length) {
      if (s[i] === "(") {
        i++;
        const inner = parseGroup();
        if (!inner) return null;
        if (i >= s.length || s[i] !== ")") return null;
        i++;
        const num = parseNumber();
        const mult = num === 0 ? 1 : num;
        for (const item of inner.elements) {
          elements.push({ el: item.el, count: item.count * mult });
        }
      } else if (s[i] === ")") {
        break;
      } else if (s[i] === "·" || s[i] === ".") {
        // Hydrate separator, skip
        i++;
      } else if (/[A-Z]/.test(s[i])) {
        let sym = s[i];
        i++;
        while (i < s.length && /[a-z]/.test(s[i])) {
          sym += s[i];
          i++;
        }
        const el = ELEMENT_MAP.get(sym);
        if (!el) return null;
        const num = parseNumber();
        elements.push({ el, count: num === 0 ? 1 : num });
      } else {
        return null;
      }
    }
    return { elements };
  }

  function parseNumber(): number {
    let numStr = "";
    while (i < s.length && /[0-9]/.test(s[i])) {
      numStr += s[i];
      i++;
    }
    return numStr ? parseInt(numStr, 10) : 0;
  }
}

function mergeElements(parsed: { el: ElementData; count: number }[]): { el: ElementData; count: number; mass: number }[] {
  const map = new Map<string, { el: ElementData; count: number }>();
  for (const { el, count } of parsed) {
    const existing = map.get(el.symbol);
    if (existing) {
      existing.count += count;
    } else {
      map.set(el.symbol, { el, count });
    }
  }
  return Array.from(map.values()).map(({ el, count }) => ({
    el,
    count,
    mass: el.mass * count,
  }));
}

// ═══════════════════════════════════════════════════════════
// Pie Chart (SVG donut)
// ═══════════════════════════════════════════════════════════

const COLORS = [
  "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#6366f1", "#14b8a6",
  "#e11d48", "#0ea5e9", "#84cc16", "#a855f7", "#d946ef",
  "#64748b", "#22d3ee", "#f43f5e",
];

function PieChart({ data }: { data: { label: string; value: number; pct: number }[] }) {
  let cum = 0;
  const slices = data.map((d, i) => {
    const startAngle = (cum / 100) * 360;
    cum += d.pct;
    const endAngle = (cum / 100) * 360;
    const largeArc = d.pct > 50 ? 1 : 0;
    const r = 80;
    const cx = 100, cy = 100;
    const x1 = cx + r * Math.cos((Math.PI / 180) * (startAngle - 90));
    const y1 = cy + r * Math.sin((Math.PI / 180) * (startAngle - 90));
    const x2 = cx + r * Math.cos((Math.PI / 180) * (endAngle - 90));
    const y2 = cy + r * Math.sin((Math.PI / 180) * (endAngle - 90));
    return { d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`, color: COLORS[i % COLORS.length], label: d.label, pct: d.pct };
  });
  return (
    <svg viewBox="0 0 200 200" className="w-full max-w-[200px] mx-auto">
      {slices.map((s, i) => (
        <path key={i} d={s.d} fill={s.color} stroke="#fff" strokeWidth="1.5" />
      ))}
      <circle cx="100" cy="100" r="40" fill="white" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool Card Wrapper
// ═══════════════════════════════════════════════════════════

function ToolCard({ icon: Icon, title, children }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2.5 bg-slate-50/50">
        <div className="w-7 h-7 rounded-lg bg-brand-100 flex items-center justify-center">
          <Icon className="w-3.5 h-3.5 text-brand-700" />
        </div>
        <h3 className="font-semibold text-sm text-slate-700">{title}</h3>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-slate-500 mb-1">{children}</label>;
}

function Input({ value, onChange, placeholder, type = "text" }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <input
      type={type}
      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent font-mono"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select
      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function ResultRow({ label, value, unit = "", highlight = false }: { label: string; value: string; unit?: string; highlight?: boolean }) {
  return (
    <div className={`flex items-center justify-between py-1.5 px-3 rounded-md ${highlight ? "bg-brand-50 border border-brand-100" : ""}`}>
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-sm font-mono font-semibold ${highlight ? "text-brand-700" : "text-slate-700"}`}>
        {value}{unit && <span className="text-xs text-slate-400 ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool 1: Molar Mass Calculator
// ═══════════════════════════════════════════════════════════

function MolarMassCalculator() {
  const [formula, setFormula] = useState("");
  const [error, setError] = useState("");

  const result = useMemo(() => {
    setError("");
    if (!formula.trim()) return null;
    const parsed = parseFormula(formula);
    if (!parsed || parsed.length === 0) {
      setError("无法解析化学式，请检查格式（如 H2SO4、Ca(OH)2）");
      return null;
    }
    const merged = mergeElements(parsed);
    const totalMass = merged.reduce((s, m) => s + m.mass, 0);
    return { elements: merged, totalMass };
  }, [formula]);

  const pieData = useMemo(() => {
    if (!result) return [];
    return result.elements.map((m) => ({
      label: m.el.symbol,
      value: m.mass,
      pct: (m.mass / result.totalMass) * 100,
    }));
  }, [result]);

  return (
    <div>
      <Label>输入化学式</Label>
      <div className="flex gap-2">
        <Input value={formula} onChange={setFormula} placeholder="例如: H2SO4, C6H12O6, Ca(OH)2" />
      </div>
      {error && <p className="text-xs text-red-500 mt-2">{error}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <ResultRow label="总摩尔质量" value={result.totalMass.toFixed(4)} unit="g/mol" highlight />
          <div className="bg-slate-50 rounded-lg border border-slate-100 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-100">
                  <th className="text-left px-3 py-2 font-medium text-slate-500">元素</th>
                  <th className="text-center px-3 py-2 font-medium text-slate-500">符号</th>
                  <th className="text-right px-3 py-2 font-medium text-slate-500">原子量</th>
                  <th className="text-right px-3 py-2 font-medium text-slate-500">数量</th>
                  <th className="text-right px-3 py-2 font-medium text-slate-500">质量 (g/mol)</th>
                  <th className="text-right px-3 py-2 font-medium text-slate-500">占比</th>
                </tr>
              </thead>
              <tbody>
                {result.elements.map(({ el, count, mass }) => (
                  <tr key={el.symbol} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-2 text-slate-600">{el.name}</td>
                    <td className="px-3 py-2 text-center font-semibold text-slate-700">{el.symbol}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-500">{el.mass.toFixed(3)}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-600">{count}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-700">{mass.toFixed(4)}</td>
                    <td className="px-3 py-2 text-right font-mono text-brand-600 font-semibold">{(mass / result.totalMass * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pieData.length > 1 && (
            <div className="flex flex-col items-center gap-2 pt-2">
              <PieChart data={pieData} />
              <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center">
                {pieData.map((d, i) => (
                  <span key={d.label} className="text-xs text-slate-500 flex items-center gap-1">
                    <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: COLORS[i % COLORS.length] }} />
                    {d.label} {d.pct.toFixed(1)}%
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool 2: Solution Prep Calculator
// ═══════════════════════════════════════════════════════════

function SolutionCalculator() {
  const [mode, setMode] = useState<"prep" | "dilute">("prep");

  // Prep mode
  const [conc, setConc] = useState("");
  const [vol, setVol] = useState("");
  const [mw, setMw] = useState("");

  // Dilute mode
  const [c1, setC1] = useState("");
  const [v1, setV1] = useState("");
  const [c2, setC2] = useState("");

  const prepResult = useMemo(() => {
    const C = parseFloat(conc);
    const V = parseFloat(vol);
    const M = parseFloat(mw);
    if (isNaN(C) || isNaN(V) || isNaN(M) || C <= 0 || V <= 0 || M <= 0) return null;
    const mass = C * (V / 1000) * M;
    return { mass, C, V, M };
  }, [conc, vol, mw]);

  const diluteResult = useMemo(() => {
    const C1 = parseFloat(c1);
    const V1 = parseFloat(v1);
    const C2 = parseFloat(c2);
    if (isNaN(C1) || isNaN(V1) || isNaN(C2) || C1 <= 0 || V1 <= 0 || C2 <= 0 || C2 >= C1) return null;
    const V2 = C1 * V1 / C2;
    const waterAdd = V2 - V1;
    return { V2, waterAdd, C1, V1, C2 };
  }, [c1, v1, c2]);

  return (
    <div>
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 mb-4">
        <button
          onClick={() => setMode("prep")}
          className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${mode === "prep" ? "bg-white text-brand-700 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
        >
          已知浓度配制
        </button>
        <button
          onClick={() => setMode("dilute")}
          className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${mode === "dilute" ? "bg-white text-brand-700 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
        >
          稀释计算
        </button>
      </div>

      {mode === "prep" ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>目标浓度 (mol/L)</Label>
              <Input value={conc} onChange={setConc} placeholder="0.1" type="number" />
            </div>
            <div>
              <Label>体积 (mL)</Label>
              <Input value={vol} onChange={setVol} placeholder="500" type="number" />
            </div>
          </div>
          <div>
            <Label>溶质分子量 MW (g/mol)</Label>
            <Input value={mw} onChange={setMw} placeholder="58.44 (NaCl)" type="number" />
          </div>
          {prepResult && (
            <div className="space-y-2 mt-3">
              <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700 font-mono border border-amber-100">
                mass = C × (V/1000) × MW = {prepResult.C} × ({prepResult.V}/1000) × {prepResult.M}
              </div>
              <ResultRow label="需要称取的质量" value={prepResult.mass.toFixed(4)} unit="g" highlight />
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>原始浓度 C₁ (mol/L)</Label>
              <Input value={c1} onChange={setC1} placeholder="1.0" type="number" />
            </div>
            <div>
              <Label>原始体积 V₁ (mL)</Label>
              <Input value={v1} onChange={setV1} placeholder="100" type="number" />
            </div>
          </div>
          <div>
            <Label>目标浓度 C₂ (mol/L)</Label>
            <Input value={c2} onChange={setC2} placeholder="0.1" type="number" />
          </div>
          {diluteResult && (
            <div className="space-y-2 mt-3">
              <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700 font-mono border border-amber-100">
                C₁V₁ = C₂V₂ → {diluteResult.C1} × {diluteResult.V1} = {diluteResult.C2} × V₂
              </div>
              <ResultRow label="目标体积 V₂" value={diluteResult.V2.toFixed(2)} unit="mL" />
              <ResultRow label="需要加水量" value={diluteResult.waterAdd.toFixed(2)} unit="mL" highlight />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool 3: pH Calculator
// ═══════════════════════════════════════════════════════════

function PHCalculator() {
  const [acidType, setAcidType] = useState("strong");
  const [conc, setConc] = useState("");
  const [ka, setKa] = useState("");

  const result = useMemo(() => {
    const C = parseFloat(conc);
    if (isNaN(C) || C <= 0) return null;

    let hPlus: number, ohMinus: number, ph: number;

    if (acidType === "strong") {
      hPlus = C;
      ph = -Math.log10(hPlus);
      ohMinus = 1e-14 / hPlus;
    } else if (acidType === "strongBase") {
      ohMinus = C;
      hPlus = 1e-14 / ohMinus;
      ph = -Math.log10(hPlus);
    } else if (acidType === "weak") {
      const Ka = parseFloat(ka);
      if (isNaN(Ka) || Ka <= 0) return null;
      hPlus = Math.sqrt(Ka * C);
      ph = -Math.log10(hPlus);
      ohMinus = 1e-14 / hPlus;
    } else {
      const Kb = parseFloat(ka);
      if (isNaN(Kb) || Kb <= 0) return null;
      ohMinus = Math.sqrt(Kb * C);
      hPlus = 1e-14 / ohMinus;
      ph = -Math.log10(hPlus);
    }
    return { hPlus, ohMinus, ph: Math.max(0, Math.min(14, ph)) };
  }, [acidType, conc, ka]);

  const phColor = useMemo(() => {
    if (!result) return "#cbd5e1";
    const ph = result.ph;
    // pH color gradient: red (0) -> orange -> yellow -> green -> blue -> purple (14)
    if (ph <= 2) return "#e11d48";
    if (ph <= 4) return "#f97316";
    if (ph <= 5.5) return "#eab308";
    if (ph <= 6.5) return "#84cc16";
    if (ph <= 7.5) return "#10b981";
    if (ph <= 9) return "#06b6d4";
    if (ph <= 11) return "#3b82f6";
    return "#8b5cf6";
  }, [result]);

  return (
    <div className="space-y-3">
      <div>
        <Label>酸/碱类型</Label>
        <Select value={acidType} onChange={setAcidType} options={[
          { value: "strong", label: "强酸 (如 HCl, H₂SO₄)" },
          { value: "strongBase", label: "强碱 (如 NaOH, KOH)" },
          { value: "weak", label: "弱酸 (需输入 Ka)" },
          { value: "weakBase", label: "弱碱 (需输入 Kb)" },
        ]} />
      </div>
      <div>
        <Label>浓度 (mol/L)</Label>
        <Input value={conc} onChange={setConc} placeholder="0.1" type="number" />
      </div>
      {(acidType === "weak" || acidType === "weakBase") && (
        <div>
          <Label>{acidType === "weak" ? "Ka 值" : "Kb 值"}</Label>
          <Input value={ka} onChange={setKa} placeholder={acidType === "weak" ? "1.8e-5 (醋酸)" : "1.8e-5"} type="number" />
        </div>
      )}

      {result && (
        <div className="space-y-3 mt-3">
          <div className="flex items-center gap-4">
            <div className="flex-1 space-y-2">
              <ResultRow label="pH" value={result.ph.toFixed(2)} highlight />
              <ResultRow label="[H⁺]" value={result.hPlus.toExponential(3)} unit="mol/L" />
              <ResultRow label="[OH⁻]" value={result.ohMinus.toExponential(3)} unit="mol/L" />
            </div>
            <div className="flex flex-col items-center gap-1 shrink-0">
              <div
                className="w-16 h-28 rounded-lg border-2 border-slate-200 flex flex-col items-center justify-center gap-0.5 shadow-sm"
                style={{ background: `linear-gradient(to bottom, ${phColor}22, ${phColor}44)` }}
              >
                <span className="text-2xl font-bold" style={{ color: phColor }}>{result.ph.toFixed(1)}</span>
                <span className="text-[10px] text-slate-400">pH</span>
              </div>
              <div className="w-16 h-3 rounded-full border border-slate-200 overflow-hidden flex">
                {[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14].map(i => {
                  const iColor = i <= 2 ? "#e11d48" : i <= 4 ? "#f97316" : i <= 5.5 ? "#eab308" : i <= 6.5 ? "#84cc16" : i <= 7.5 ? "#10b981" : i <= 9 ? "#06b6d4" : i <= 11 ? "#3b82f6" : "#8b5cf6";
                  const active = Math.round(result.ph) === i;
                  return <div key={i} className="flex-1" style={{ background: iColor, opacity: active ? 1 : 0.3 }} />;
                })}
              </div>
              <div className="flex justify-between w-16 text-[9px] text-slate-400">
                <span>0</span><span>7</span><span>14</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool 4: Unit Converter
// ═══════════════════════════════════════════════════════════

type UnitCategory = "energy" | "pressure" | "temperature" | "wavelength";

const UNIT_DATA: Record<UnitCategory, { units: string[]; toBase: (v: number, from: string) => number; fromBase: (v: number, to: string) => number }> = {
  energy: {
    units: ["eV", "kJ/mol", "kcal/mol", "cm⁻¹"],
    toBase: (v, from) => {
      // Convert to eV
      if (from === "eV") return v;
      if (from === "kJ/mol") return v / 96.485;
      if (from === "kcal/mol") return v / 23.061;
      if (from === "cm⁻¹") return v / 8065.5;
      return v;
    },
    fromBase: (v, to) => {
      if (to === "eV") return v;
      if (to === "kJ/mol") return v * 96.485;
      if (to === "kcal/mol") return v * 23.061;
      if (to === "cm⁻¹") return v * 8065.5;
      return v;
    },
  },
  pressure: {
    units: ["atm", "Pa", "bar", "mmHg"],
    toBase: (v, from) => {
      if (from === "atm") return v;
      if (from === "Pa") return v / 101325;
      if (from === "bar") return v / 1.01325;
      if (from === "mmHg") return v / 760;
      return v;
    },
    fromBase: (v, to) => {
      if (to === "atm") return v;
      if (to === "Pa") return v * 101325;
      if (to === "bar") return v * 1.01325;
      if (to === "mmHg") return v * 760;
      return v;
    },
  },
  temperature: {
    units: ["°C", "K", "°F"],
    toBase: (v, from) => {
      // Convert to Celsius
      if (from === "°C") return v;
      if (from === "K") return v - 273.15;
      if (from === "°F") return (v - 32) * 5 / 9;
      return v;
    },
    fromBase: (v, to) => {
      if (to === "°C") return v;
      if (to === "K") return v + 273.15;
      if (to === "°F") return v * 9 / 5 + 32;
      return v;
    },
  },
  wavelength: {
    units: ["nm", "Hz", "cm⁻¹"],
    toBase: (v, from) => {
      const c = 299792458; // m/s
      if (from === "nm") return v;
      if (from === "Hz") return (c / v) * 1e9;
      if (from === "cm⁻¹") return 1e7 / v;
      return v;
    },
    fromBase: (v, to) => {
      const c = 299792458;
      if (to === "nm") return v;
      if (to === "Hz") return (c / (v * 1e-9));
      if (to === "cm⁻¹") return 1e7 / v;
      return v;
    },
  },
};

function UnitConverter() {
  const [category, setCategory] = useState<UnitCategory>("energy");
  const [fromUnit, setFromUnit] = useState("eV");
  const [toUnit, setToUnit] = useState("kJ/mol");
  const [value, setValue] = useState("1");

  const data = UNIT_DATA[category];

  const result = useMemo(() => {
    const v = parseFloat(value);
    if (isNaN(v)) return null;
    const base = data.toBase(v, fromUnit);
    return data.fromBase(base, toUnit);
  }, [value, fromUnit, toUnit, data]);

  return (
    <div className="space-y-3">
      <div>
        <Label>换算类别</Label>
        <Select value={category} onChange={(v) => { setCategory(v as UnitCategory); setFromUnit(UNIT_DATA[v as UnitCategory].units[0]); setToUnit(UNIT_DATA[v as UnitCategory].units[1]); }} options={[
          { value: "energy", label: "能量 (eV ↔ kJ/mol ↔ kcal/mol ↔ cm⁻¹)" },
          { value: "pressure", label: "压强 (atm ↔ Pa ↔ bar ↔ mmHg)" },
          { value: "temperature", label: "温度 (°C ↔ K ↔ °F)" },
          { value: "wavelength", label: "波长/频率 (nm ↔ Hz ↔ cm⁻¹)" },
        ]} />
      </div>
      <div className="grid grid-cols-[1fr,auto,1fr] gap-2 items-end">
        <div>
          <Label>输入值</Label>
          <div className="flex gap-1.5">
            <Input value={value} onChange={setValue} placeholder="1" type="number" />
            <Select value={fromUnit} onChange={setFromUnit} options={data.units.map((u) => ({ value: u, label: u }))} />
          </div>
        </div>
        <div className="pb-2 text-slate-400 text-lg">=</div>
        <div>
          <Label>输出值</Label>
          <div className="flex gap-1.5">
            <div className="w-full bg-brand-50 border border-brand-200 rounded-lg px-3 py-2 text-sm font-mono font-semibold text-brand-700 flex items-center">
              {result !== null ? (Number.isInteger(result) ? result.toString() : result.toPrecision(6)) : "—"}
            </div>
            <Select value={toUnit} onChange={setToUnit} options={data.units.map((u) => ({ value: u, label: u }))} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Tool 5: Periodic Table
// ═══════════════════════════════════════════════════════════

const CATEGORY_COLORS: Record<string, string> = {
  "碱金属": "bg-red-100 border-red-300 text-red-700",
  "碱土金属": "bg-orange-100 border-orange-300 text-orange-700",
  "过渡金属": "bg-amber-100 border-amber-300 text-amber-700",
  "金属": "bg-yellow-100 border-yellow-300 text-yellow-700",
  "非金属": "bg-green-100 border-green-300 text-green-700",
  "卤素": "bg-cyan-100 border-cyan-300 text-cyan-700",
  "稀有气体": "bg-blue-100 border-blue-300 text-blue-700",
  "镧系": "bg-purple-100 border-purple-300 text-purple-700",
  "锕系": "bg-pink-100 border-pink-300 text-pink-700",
};

// ── Helpers for element detail card ──

function parseOxStates(oxStates: string): string[] {
  return oxStates.split(",").map((s) => s.trim());
}

function oxStateColor(state: string): string {
  if (state === "0") return "bg-slate-100 text-slate-500 border-slate-200";
  if (state.startsWith("+")) return "bg-blue-50 text-blue-600 border-blue-200";
  if (state.startsWith("-")) return "bg-red-50 text-red-500 border-red-200";
  return "bg-slate-100 text-slate-500 border-slate-200";
}

const SUPER_DIGITS: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
  "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
};

function renderConfig(config: string): React.ReactNode {
  const parts: (string | React.ReactElement)[] = [];
  let i = 0;
  while (i < config.length) {
    if (SUPER_DIGITS[config[i]]) {
      let digits = "";
      while (i < config.length && SUPER_DIGITS[config[i]]) {
        digits += SUPER_DIGITS[config[i]];
        i++;
      }
      parts.push(<sup key={i - digits.length}>{digits}</sup>);
    } else {
      parts.push(config[i]);
      i++;
    }
  }
  return <>{parts}</>;
}

// ── Period / Group helpers ──

// Element Z → IUPAC group number (1-18)
const ELEMENT_GROUP: Record<number, number> = {
  1: 1, 2: 18,
  3: 1, 4: 2, 5: 13, 6: 14, 7: 15, 8: 16, 9: 17, 10: 18,
  11: 1, 12: 2, 13: 13, 14: 14, 15: 15, 16: 16, 17: 17, 18: 18,
  19: 1, 20: 2, 21: 3, 22: 4, 23: 5, 24: 6, 25: 7, 26: 8,
  27: 9, 28: 10, 29: 11, 30: 12, 31: 13, 32: 14, 33: 15, 34: 16, 35: 17, 36: 18,
  37: 1, 38: 2, 39: 3, 40: 4, 41: 5, 42: 6, 43: 7, 44: 8,
  45: 9, 46: 10, 47: 11, 48: 12, 49: 13, 50: 14, 51: 15, 52: 16, 53: 17, 54: 18,
  55: 1, 56: 2, 57: 3, 58: 3, 59: 3, 60: 3, 62: 3, 63: 3, 64: 3, 65: 3,
  66: 3, 67: 3, 68: 3, 69: 3, 70: 3, 71: 3,
  72: 4, 73: 5, 74: 6, 75: 7, 76: 8, 77: 9, 78: 10, 79: 11, 80: 12,
  81: 13, 82: 14, 83: 15, 84: 16, 86: 18,
  87: 1, 88: 2, 90: 3, 92: 3, 94: 3,
};

function getPeriod(z: number): number {
  if (z <= 2) return 1;
  if (z <= 10) return 2;
  if (z <= 18) return 3;
  if (z <= 36) return 4;
  if (z <= 54) return 5;
  if (z <= 86) return 6;
  return 7;
}

// Format helpers for table cells
function fmtMass(m: number) { return m.toFixed(1); }
function fmtTemp(t: number | null) { return t !== null ? t.toString() : "—"; }
function fmtEneg(e: number | null) { return e !== null ? e.toFixed(2) : "—"; }

function getElementCategoryDesc(el: ElementData): string {
  const p = getPeriod(el.z);
  const g = ELEMENT_GROUP[el.z];
  let desc = `第 ${p} 周期${el.category}`;
  const pge = [44, 45, 46, 76, 77, 78]; // Ru, Rh, Pd, Os, Ir, Pt
  if (pge.includes(el.z)) desc += " · 铂族元素";
  else if (g >= 3 && g <= 12 && el.category === "过渡金属") desc += ` · 第 ${g} 族`;
  return desc;
}

// ── Comparison table component ──

function GroupRadarChart({ selectedZ, group }: { selectedZ: number; group: number }) {
  const groupEls = ELEMENTS
    .filter((el) => ELEMENT_GROUP[el.z] === group)
    .sort((a, b) => a.z - b.z);

  const ranges = useMemo(() => {
    const masses = ELEMENTS.map((e) => e.mass);
    const mps = ELEMENTS.filter((e) => e.mp !== null).map((e) => e.mp!);
    const bps = ELEMENTS.filter((e) => e.bp !== null).map((e) => e.bp!);
    const enegs = ELEMENTS.filter((e) => e.eneg !== null).map((e) => e.eneg!);
    const zs = ELEMENTS.map((e) => e.z);
    return {
      mass: { min: Math.min(...masses), max: Math.max(...masses) },
      mp: { min: Math.min(...mps), max: Math.max(...mps) },
      bp: { min: Math.min(...bps), max: Math.max(...bps) },
      eneg: { min: Math.min(...enegs), max: Math.max(...enegs) },
      z: { min: Math.min(...zs), max: Math.max(...zs) },
    };
  }, []);

  const normalize = (v: number, r: { min: number; max: number }) =>
    r.max === r.min ? 50 : ((v - r.min) / (r.max - r.min)) * 100;

  const chartData = [
    { axis: "原子量", ...Object.fromEntries(groupEls.map((el) => [el.symbol, normalize(el.mass, ranges.mass)])) },
    { axis: "熔点", ...Object.fromEntries(groupEls.map((el) => [el.symbol, el.mp !== null ? normalize(el.mp, ranges.mp) : 0])) },
    { axis: "沸点", ...Object.fromEntries(groupEls.map((el) => [el.symbol, el.bp !== null ? normalize(el.bp, ranges.bp) : 0])) },
    { axis: "电负性", ...Object.fromEntries(groupEls.map((el) => [el.symbol, el.eneg !== null ? normalize(el.eneg, ranges.eneg) : 0])) },
    { axis: "原子序数", ...Object.fromEntries(groupEls.map((el) => [el.symbol, normalize(el.z, ranges.z)])) },
  ];

  const maxEls = 10;
  const displayEls = groupEls.length > maxEls
    ? groupEls.filter((el) => el.z === selectedZ || groupEls.indexOf(el) < maxEls)
    : groupEls;

  const CHART_COLORS = ["#F59E0B", "#10B981", "#8B5CF6", "#EF4444", "#EC4899", "#06B6D4", "#F97316", "#6366F1"];

  return (
    <div className="w-full flex flex-col items-center">
      <div className="text-xs font-semibold text-slate-500 mb-1">同族元素对比</div>
      <ResponsiveContainer width="100%" height={300}>
        <RadarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 10, fill: "#94a3b8" }} />
          <PolarRadiusAxis tick={false} axisLine={false} />
          {displayEls.map((el, i) => {
            const selected = el.z === selectedZ;
            const color = selected ? "#2563EB" : CHART_COLORS[i % CHART_COLORS.length];
            return (
              <Radar
                key={el.symbol}
                name={el.symbol}
                dataKey={el.symbol}
                stroke={color}
                fill={color}
                fillOpacity={0.15}
                strokeWidth={selected ? 3 : 1.5}
                dot={selected}
              />
            );
          })}
        </RadarChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5 mt-1">
        {displayEls.map((el, i) => {
          const selected = el.z === selectedZ;
          const color = selected ? "#2563EB" : CHART_COLORS[i % CHART_COLORS.length];
          return (
            <span key={el.symbol} className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
              <span className={`text-xs font-mono ${selected ? "font-bold" : ""}`} style={{ color }}>
                {el.symbol}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

function DetailCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded-lg px-2.5 py-2.5 text-center border border-slate-100">
      <div className="text-xs text-slate-400 mb-0.5">{label}</div>
      <div className="text-sm font-mono font-semibold text-slate-700">{value}</div>
    </div>
  );
}

function PeriodicTable() {
  const [selected, setSelected] = useState<ElementData | null>(null);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return ELEMENTS;
    const q = search.toLowerCase();
    return ELEMENTS.filter(
      (el) =>
        el.name.includes(q) ||
        el.symbol.toLowerCase().includes(q) ||
        el.z.toString() === q
    );
  }, [search]);

  // Grid layout: period 1-7, group 1-18 (with gaps for lanthanides/actinides)
  // We'll use a simple wrapped grid for the search results / full view

  const showSearchResults = search.trim().length > 0;

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
        <input
          className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          placeholder="搜索元素名称或符号 (如 Fe, 碳, 26)..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {search && (
          <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {showSearchResults ? (
        <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
          {filtered.slice(0, 30).map((el) => (
            <button
              key={el.symbol}
              onClick={() => setSelected(el)}
              className={`w-full text-left px-3 py-2 text-sm border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors flex items-center gap-2.5 ${
                selected?.symbol === el.symbol ? "bg-brand-50" : ""
              }`}
            >
              <span className={`inline-flex items-center justify-center w-8 h-8 rounded border text-xs font-bold ${CATEGORY_COLORS[el.category] || "bg-slate-100 border-slate-300 text-slate-600"}`}>
                {el.symbol}
              </span>
              <span className="flex-1">
                <span className="font-medium text-slate-700">{el.name}</span>
                <span className="text-xs text-slate-400 ml-1.5">Z={el.z}</span>
              </span>
              <span className="text-xs text-slate-400 font-mono">{el.mass.toFixed(2)}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="relative">
          {/* Periodic table layout */}
          <div className="text-xs text-slate-400 mb-2 text-center">点击元素查看详细信息 | 共 {ELEMENTS.length} 个元素</div>
          <div className="overflow-x-auto">
            <div className="grid gap-0.5" style={{ minWidth: 700 }}>
              {/* This is a simplified periodic table layout grid */}
              <PeriodicGrid onSelect={setSelected} selected={selected} />
            </div>
          </div>
          <div className="text-[10px] text-slate-400 text-center mt-1">简版周期表 | 镧系锕系元素已省略</div>
        </div>
      )}

      {selected && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
          {/* Left — element info card */}
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 h-full flex flex-col">
            <div className="flex items-center gap-3 mb-4">
              <span className={`inline-flex items-center justify-center w-12 h-12 rounded-xl border-2 text-lg font-bold ${CATEGORY_COLORS[selected.category] || ""}`}>
                {selected.symbol}
              </span>
              <div>
                <div className="font-semibold text-slate-800 text-base">{selected.name} ({selected.symbol})</div>
                <div className="text-[15px] text-slate-400">{ELEMENT_EN[selected.symbol]}</div>
                <div className="text-sm text-slate-500">{selected.category} · Z={selected.z}</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-3">
              <DetailCard label="原子序数" value={selected.z.toString()} />
              <DetailCard label="原子量" value={selected.mass.toFixed(2)} />
              <DetailCard label="电负性" value={selected.eneg !== null ? selected.eneg.toFixed(2) : "—"} />
              <DetailCard label="熔点" value={selected.mp !== null ? `${selected.mp} °C` : "—"} />
              <DetailCard label="沸点" value={selected.bp !== null ? `${selected.bp} °C` : "—"} />
              <div className="bg-slate-50 rounded-lg px-2.5 py-2 text-center border border-slate-100">
                <div className="text-[11px] text-slate-400 mb-0.5">电子构型</div>
                <div className="text-[13px] font-mono font-semibold text-slate-700 break-all leading-tight">
                  {renderConfig(selected.config)}
                </div>
              </div>
            </div>

            <div className="space-y-1.5 mb-3">
              <p className="text-[15px] text-slate-500 leading-relaxed">{getElementCategoryDesc(selected)}</p>
              <p className="text-[15px] text-slate-500 leading-relaxed">{ELEMENT_USES[selected.symbol]}</p>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap mt-auto">
              <span className="text-[14px] text-slate-400 shrink-0">常见氧化态</span>
              {parseOxStates(selected.oxStates).map((state, i) => (
                <span
                  key={i}
                  className={`inline-block text-[13px] font-mono font-semibold px-2.5 py-1 rounded-full border ${oxStateColor(state)}`}
                >
                  {state}
                </span>
              ))}
            </div>
          </div>

          {/* Right — group radar chart */}
          <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 h-full flex flex-col items-center justify-center">
            <GroupRadarChart selectedZ={selected.z} group={ELEMENT_GROUP[selected.z]} />
          </div>
        </div>
      )}
    </div>
  );
}

// Simplified periodic table layout
function PeriodicGrid({ onSelect, selected }: { onSelect: (el: ElementData) => void; selected: ElementData | null }) {
  // Period 1-6 main groups, omitting f-block for compactness
  // Layout: rows = periods, columns = groups
  // We'll show only the s and p blocks + some d-block
  // Using a simplified approach: show 8 main groups (1,2,13-18) + some transition metals

  const layout: (ElementData | null)[][] = [
    // Period 1
    [getEl(1), null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null, getEl(2)],
    // Period 2
    [getEl(3), getEl(4),null,null,null,null,null,null,null,null,null,null, getEl(5), getEl(6), getEl(7), getEl(8), getEl(9), getEl(10)],
    // Period 3
    [getEl(11),getEl(12),null,null,null,null,null,null,null,null,null,null,getEl(13),getEl(14),getEl(15),getEl(16),getEl(17),getEl(18)],
    // Period 4
    [getEl(19),getEl(20),getEl(21),getEl(22),getEl(23),getEl(24),getEl(25),getEl(26),getEl(27),getEl(28),getEl(29),getEl(30),getEl(31),getEl(32),getEl(33),getEl(34),getEl(35),getEl(36)],
    // Period 5
    [getEl(37),getEl(38),getEl(39),getEl(40),getEl(41),getEl(42),getEl(43),getEl(44),getEl(45),getEl(46),getEl(47),getEl(48),getEl(49),getEl(50),getEl(51),getEl(52),getEl(53),getEl(54)],
    // Period 6
    [getEl(55),getEl(56),getEl(71),getEl(72),getEl(73),getEl(74),getEl(75),getEl(76),getEl(77),getEl(78),getEl(79),getEl(80),getEl(81),getEl(82),getEl(83),getEl(84),null,getEl(86)],
  ];

  return (
    <div className="grid gap-0.5" style={{ gridTemplateColumns: "repeat(18, 1fr)" }}>
      {/* Group headers */}
      {[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18].map((g) => (
        <div key={g} className="text-[9px] text-slate-400 text-center py-0.5">{g}</div>
      ))}
      {layout.map((row, ri) =>
        row.map((el, ci) => (
          <div key={`${ri}-${ci}`} className="aspect-square flex items-center justify-center">
            {el ? (
              <button
                onClick={() => onSelect(el)}
                className={`w-full h-full rounded border text-[10px] font-bold flex flex-col items-center justify-center leading-tight transition-all ${
                  CATEGORY_COLORS[el.category] || "bg-slate-100 border-slate-300 text-slate-600"
                } ${selected?.symbol === el.symbol ? "ring-2 ring-brand-500 scale-110 z-10" : "hover:scale-110 hover:z-10"}`}
                title={`${el.name} (${el.symbol}) Z=${el.z}`}
              >
                <span className="text-[8px] leading-none text-slate-400">{el.z}</span>
                <span>{el.symbol}</span>
              </button>
            ) : (
              <span className="w-full h-full" />
            )}
          </div>
        ))
      )}
    </div>
  );
}

function getEl(z: number): ElementData | null {
  return ELEMENTS.find((e) => e.z === z) || null;
}

// ═══════════════════════════════════════════════════════════
// Tool 6: Buffer Calculator (Henderson-Hasselbalch)
// ═══════════════════════════════════════════════════════════

const BUFFER_PRESETS: { name: string; pKa: number; acid: string; base: string }[] = [
  { name: "醋酸/醋酸钠", pKa: 4.76, acid: "CH₃COOH", base: "CH₃COONa" },
  { name: "磷酸盐 (H₂PO₄⁻/HPO₄²⁻)", pKa: 7.21, acid: "NaH₂PO₄", base: "Na₂HPO₄" },
  { name: "Tris-HCl", pKa: 8.07, acid: "Tris-HCl", base: "Tris" },
  { name: "柠檬酸/柠檬酸钠 (pKa₁)", pKa: 3.13, acid: "柠檬酸", base: "柠檬酸钠" },
  { name: "碳酸/碳酸氢钠", pKa: 6.37, acid: "H₂CO₃", base: "NaHCO₃" },
  { name: "氨/氯化铵", pKa: 9.25, acid: "NH₄Cl", base: "NH₃" },
  { name: "甘氨酸 (pKa₂)", pKa: 9.78, acid: "NH₃⁺-CH₂-COO⁻", base: "NH₂-CH₂-COO⁻" },
];

function BufferCalculator() {
  const [pKa, setPka] = useState("4.76");
  const [concHA, setConcHA] = useState("0.1");
  const [concA, setConcA] = useState("0.1");
  const [selectedPreset, setSelectedPreset] = useState("");

  const handlePreset = (name: string) => {
    const preset = BUFFER_PRESETS.find((p) => p.name === name);
    if (preset) {
      setPka(preset.pKa.toString());
      setSelectedPreset(name);
    }
  };

  const result = useMemo(() => {
    const pKaV = parseFloat(pKa);
    const ha = parseFloat(concHA);
    const a = parseFloat(concA);
    if (isNaN(pKaV) || isNaN(ha) || isNaN(a) || ha <= 0 || a <= 0) return null;
    const ratio = a / ha;
    const logRatio = Math.log10(ratio);
    const pH = pKaV + logRatio;
    return { pH: Math.max(0, Math.min(14, pH)), ratio, logRatio };
  }, [pKa, concHA, concA]);

  return (
    <div className="space-y-3">
      <div>
        <Label>常用缓冲体系</Label>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {BUFFER_PRESETS.map((p) => (
            <button
              key={p.name}
              onClick={() => handlePreset(p.name)}
              className={`text-[11px] px-2 py-1 rounded-md border transition-colors ${
                selectedPreset === p.name
                  ? "bg-brand-100 border-brand-300 text-brand-700 font-medium"
                  : "bg-white border-slate-200 text-slate-500 hover:border-slate-300"
              }`}
            >
              {p.name.split(" ")[0]}
            </button>
          ))}
        </div>
        {selectedPreset && (
          <div className="text-xs text-slate-500 bg-amber-50 rounded-md p-2 border border-amber-100">
            {BUFFER_PRESETS.find((p) => p.name === selectedPreset)?.acid} / {BUFFER_PRESETS.find((p) => p.name === selectedPreset)?.base}
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div>
          <Label>pKa</Label>
          <Input value={pKa} onChange={setPka} placeholder="4.76" type="number" />
        </div>
        <div>
          <Label>[HA] 弱酸浓度</Label>
          <Input value={concHA} onChange={setConcHA} placeholder="0.1" type="number" />
        </div>
        <div>
          <Label>[A⁻] 共轭碱浓度</Label>
          <Input value={concA} onChange={setConcA} placeholder="0.1" type="number" />
        </div>
      </div>

      {result && (
        <div className="space-y-2 mt-3">
          <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700 font-mono border border-amber-100">
            pH = pKa + log([A⁻]/[HA]) = {pKa} + log({concA}/{concHA}) = {pKa} + ({result.logRatio >= 0 ? "+" : ""}{result.logRatio.toFixed(4)})
          </div>
          <ResultRow label="pH" value={result.pH.toFixed(2)} highlight />
          <ResultRow label="[A⁻]/[HA] 比值" value={result.ratio.toFixed(4)} />
          <div className="text-xs text-slate-400">
            {result.ratio >= 0.1 && result.ratio <= 10
              ? "有效缓冲范围 (0.1 ≤ [A⁻]/[HA] ≤ 10)"
              : "⚠ 超出有效缓冲范围，建议调整浓度"}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Navigation
// ═══════════════════════════════════════════════════════════

type ToolId = "molar-mass" | "solution" | "ph" | "unit" | "periodic" | "buffer";

const TOOL_INFO: { id: ToolId; name: string; icon: React.ComponentType<{ className?: string }>; desc: string }[] = [
  { id: "molar-mass", name: "摩尔质量计算器", icon: Calculator, desc: "计算化学式的摩尔质量和质量组成百分比" },
  { id: "solution", name: "溶液配制计算器", icon: Beaker, desc: "计算配制目标浓度溶液所需的溶质质量" },
  { id: "ph", name: "pH 计算器", icon: Droplets, desc: "计算强酸、弱酸和碱溶液的 pH 值" },
  { id: "unit", name: "单位换算", icon: ArrowLeftRight, desc: "能量、压强、温度、波长等常见单位换算" },
  { id: "periodic", name: "元素周期表查询", icon: Search, desc: "查询元素的详细信息、电子构型、物理性质等" },
  { id: "buffer", name: "缓冲溶液计算器", icon: FlaskConical, desc: "使用 Henderson-Hasselbalch 方程计算缓冲液 pH" },
];

function renderTool(id: ToolId) {
  switch (id) {
    case "molar-mass": return <MolarMassCalculator />;
    case "solution": return <SolutionCalculator />;
    case "ph": return <PHCalculator />;
    case "unit": return <UnitConverter />;
    case "periodic": return <PeriodicTable />;
    case "buffer": return <BufferCalculator />;
  }
}

// ═══════════════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════════════

export default function ChemistryToolbox() {
  const [selected, setSelected] = useState<ToolId | null>(null);

  if (selected) {
    const info = TOOL_INFO.find((t) => t.id === selected)!;
    const Icon = info.icon;
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-slate-800">化学计算工具箱</h1>
            <p className="text-sm text-slate-500 mt-1">实用化学计算工具集</p>
          </div>
        </div>
        <button
          onClick={() => setSelected(null)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 mb-4 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          返回工具箱
        </button>
        <ToolCard icon={Icon} title={info.name}>
          {renderTool(selected)}
        </ToolCard>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-800">化学计算工具箱</h1>
          <p className="text-sm text-slate-500 mt-1">选择工具开始使用</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {TOOL_INFO.map((tool) => {
          const Icon = tool.icon;
          return (
            <button
              key={tool.id}
              onClick={() => setSelected(tool.id)}
              className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 hover:border-blue-300 hover:shadow-md transition-all text-left group"
            >
              <div className="w-10 h-10 rounded-lg bg-brand-100 flex items-center justify-center mb-3 group-hover:bg-brand-200 transition-colors">
                <Icon className="w-5 h-5 text-brand-700" />
              </div>
              <div className="font-semibold text-sm text-slate-800 mb-1">{tool.name}</div>
              <div className="text-xs text-slate-500 leading-relaxed">{tool.desc}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
