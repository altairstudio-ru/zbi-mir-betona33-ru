export interface ZbiProduct {
  name: string;
  price: string;
}

export interface FbsBlock {
  mark: string;
  length: number;
  width: number;
  height: number;
  weight: number;
  price: number;
}

export const zbiProducts: ZbiProduct[] = [
  { name: 'Фундаментные блоки (ФБС)', price: 'от 4 200 ₽/шт' },
  { name: 'Плиты перекрытия ПК / ПБ', price: 'от 6 800 ₽/шт' },
  { name: 'Бетон товарный (М100–М400)', price: 'от 4 900 ₽/м³' },
  { name: 'Кольца колодезные, лотки', price: 'от 3 100 ₽/шт' },
  { name: 'Брусчатка, бордюры', price: 'от 950 ₽/м²' },
  { name: 'Сваи, балки, перемычки', price: 'по чертежу' },
];

export const fbsBlocks: FbsBlock[] = [
  { mark: 'ФБС 6-6-6',   length: 580,  width: 600, height: 580, weight: 540,  price: 1761 },
  { mark: 'ФБС 8-6-6',   length: 780,  width: 600, height: 580, weight: 570,  price: 2283 },
  { mark: 'ФБС 9-3-3',   length: 880,  width: 300, height: 280, weight: 190,  price: 853 },
  { mark: 'ФБС 9-4-3',   length: 880,  width: 400, height: 280, weight: 250,  price: 864 },
  { mark: 'ФБС 9-5-3',   length: 880,  width: 500, height: 280, weight: 270,  price: 1122 },
  { mark: 'ФБС 9-6-3',   length: 880,  width: 600, height: 280, weight: 380,  price: 1316 },
  { mark: 'ФБС 9-3-6',   length: 880,  width: 300, height: 580, weight: 320,  price: 1319 },
  { mark: 'ФБС 9-4-6',   length: 880,  width: 400, height: 580, weight: 480,  price: 1708 },
  { mark: 'ФБС 9-5-6',   length: 880,  width: 500, height: 580, weight: 540,  price: 2094 },
  { mark: 'ФБС 9-6-6',   length: 880,  width: 600, height: 580, weight: 640,  price: 2540 },
  { mark: 'ФБС 12-3-3',  length: 1180, width: 300, height: 280, weight: 240,  price: 985 },
  { mark: 'ФБС 12-3-6',  length: 1180, width: 300, height: 580, weight: 455,  price: 1747 },
  { mark: 'ФБС 12-4-3',  length: 1180, width: 400, height: 280, weight: 280,  price: 1173 },
  { mark: 'ФБС 12-4-6',  length: 1180, width: 400, height: 580, weight: 580,  price: 2318 },
  { mark: 'ФБС 12-5-3',  length: 1180, width: 500, height: 280, weight: 380,  price: 1423 },
  { mark: 'ФБС 12-5-6',  length: 1180, width: 500, height: 580, weight: 790,  price: 2868 },
  { mark: 'ФБС 12-6-3',  length: 1180, width: 600, height: 280, weight: 460,  price: 1675 },
  { mark: 'ФБС 12-6-6',  length: 1180, width: 600, height: 580, weight: 880,  price: 3399 },
  { mark: 'ФБС 24-3-6',  length: 2380, width: 300, height: 580, weight: 900,  price: 3471 },
  { mark: 'ФБС 24-4-6',  length: 2380, width: 400, height: 580, weight: 1200, price: 4555 },
  { mark: 'ФБС 24-5-6',  length: 2380, width: 500, height: 580, weight: 1500, price: 5723 },
  { mark: 'ФБС 24-6-6',  length: 2380, width: 600, height: 580, weight: 1800, price: 6765 },
];

export const stats = [
  { number: '18', label: 'лет на рынке' },
  { number: '120 000 м³', label: 'в год — оборот производства' },
  { number: '340', label: 'сданных объектов' },
  { number: 'от 3 дней', label: 'от заявки до отгрузки' },
];

export const aboutStats = [
  { number: '2 линии', label: 'бетон + ЖБИ' },
  { number: '24/7', label: 'отгрузка в выходные' },
  { number: '12 000 м²', label: 'склад готовой продукции' },
  { number: '12 машин', label: 'свой автопарк' },
];

export const steps = [
  { number: 1, title: 'Заявка и расчёт', description: 'Присылаете план или размеры. Считаем объём, марку, стоимость за 1 день.' },
  { number: 2, title: 'Согласование', description: 'Подбираем марку под ваш грунт и нагрузку. Фиксируем цену в договоре.' },
  { number: 3, title: 'Доставка', description: 'Привозим своим транспортом в назначенный день. С паспортом партии.' },
  { number: 4, title: 'Монтаж и контроль', description: 'По запросу — наша бригада делает укладку. Контроль качества на каждом этапе.' },
];

export const reviews = [
  {
    text: 'Заказывали ФБС на фундамент дома. Привезли точно в день, марка в паспорте совпала. Цена не выросла за неделю, пока ждали технику.',
    name: 'Андрей',
    role: 'Частный заказчик, Суздальский район',
  },
  {
    text: 'Работаем вторую зиму. График отгрузок не срывают, документы в порядке, лаборатория приезжает на объект. Для подрядчика это критично.',
    name: 'Сергей',
    role: 'Прораб, Ковров',
  },
  {
    text: 'Брали бетон М300 на площадку. 12 машин за 2 дня, без накладок. По объёму — ровно столько, сколько в накладной.',
    name: 'Дмитрий',
    role: 'Строитель, Гусь-Хрустальный',
  },
];

export const faqItems = [
  {
    question: 'Какие марки бетона вы производите?',
    answer: 'Мы производим товарный бетон от М100 до М400, а также специальные марки по запросу. Все марки соответствуют ГОСТ и сопровождаются паспортом партии.',
  },
  {
    question: 'Сколько времени занимает доставка?',
    answer: 'Стандартная доставка — от 1 до 3 рабочих дней в зависимости от объёма и загруженности производства. Срочные заказы — в день обращения.',
  },
  {
    question: 'Какие документы выдаёте на продукцию?',
    answer: 'Паспорт партии, сертификат соответствия, ТТН. Полный пакет документов для подрядчиков и инвесторов.',
  },
  {
    question: 'Можете изготовить нестандартные размеры ФБС?',
    answer: 'Да, изготовим по вашему чертежу от 50 штук. Срок — от 7 рабочих дней. Консультация и расчёт — бесплатно.',
  },
  {
    question: 'Как рассчитать стоимость доставки?',
    answer: 'Стоимость доставки зависит от расстояния и объёма. По Владимиру — от 0 ₽. По области — расчёт по километражу. Позвоните нам для точного расчёта.',
  },
  {
    question: 'Работаете ли вы в выходные?',
    answer: 'Да, отгрузка работает 24/7, включая выходные и праздники. Заказывайте доставку на удобное время.',
  },
];
