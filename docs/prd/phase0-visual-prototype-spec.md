# دستور طراحی پوسته نمایشی پلتفرم «یادگیری، پژوهش، همکاری و حل مسئله»

## نقش شما

در این مرحله شما فقط به‌عنوان:

- Senior Product Designer
- UX/UI Architect
- Information Architect
- EdTech Product Designer
- Business Platform Designer
- AI-Native Product Architect

عمل می‌کنید.

هدف این مرحله فقط **طراحی مفهومی، معماری اطلاعات، UX، UI، Wireframe و Mockup نمایشی** است.

---

# 🚨 محدودیت بسیار مهم این مرحله

در این مرحله تحت هیچ شرایطی:

- کدنویسی نکن
- HTML/CSS/JS ایجاد نکن
- Backend ایجاد نکن
- Database ایجاد نکن
- API ایجاد نکن
- Authentication پیاده نکن
- GitHub را تغییر نده
- Package نصب نکن
- فایل‌های پروژه را تغییر نده
- Migration انجام نده
- Deployment انجام نده
- Commit ایجاد نکن
- هیچ قابلیت واقعی را اجرا نکن

من فعلاً فقط می‌خواهم **پوسته و تجربه کاربری سایت را ببینم و درباره آن تصمیم بگیرم.**

اگر برای نمایش چیزی نیاز به Prototype داری، فقط در حد **Mockup / Wireframe / Visual Prototype** ارائه کن و وارد Implementation نشو.

پس از تأیید صریح من، وارد مرحله معماری فنی و سپس کدنویسی خواهیم شد.

---

# 1. ایده اصلی محصول

این محصول نباید از نظر ظاهری صرفاً یک:

- سایت استاد
- سایت دانشجویان
- LMS
- سایت طراحی سایت
- شرکت خدمات IT
- سایت مشاوره
- سایت فریلنسری

به نظر برسد.

این یک پلتفرم یکپارچه برای:

> **یادگیری + پژوهش + توسعه مهارت + همکاری + حل مسئله + اجرای کار واقعی**

است.

فلسفه کلی:

> **یاد بگیر، مهارت بساز و خودت انجام بده؛ یا مسئله و نیازت را برای حل به ما بسپار.**

زیرعنوان پیشنهادی:

> آموزش، پژوهش، همکاری و توسعه راه‌حل‌های واقعی؛ از ایده تا اجرا.

---

# 2. سه نیت اصلی کاربر

هر فرد پس از ورود باید بتواند خیلی سریع مسیر خود را مشخص کند.

## مسیر اول — 📚 یادگیری و رشد

برای:

- دانشجوی ترم
- دانشجوی آزاد
- یادگیرنده عمومی
- پژوهشگر
- فردی که می‌خواهد مهارت کسب کند
- فردی که می‌خواهد برای ورود به بازار کار آماده شود

---

## مسیر دوم — 💼 طرح مسئله / نیاز

برای:

- شخص حقیقی
- شرکت خصوصی
- سازمان
- نهاد دولتی
- شهرداری
- دانشگاه
- پژوهشگر
- دانشجوی دانشگاه دیگر
- کارآفرین
- صاحب کسب‌وکار
- هر فردی که مسئله یا نیازی دارد

مسئله می‌تواند بسیار گسترده باشد.

هرگز سایت را به کلمه «پروژه» محدود نکن.

نمونه حوزه‌ها:

- برنامه‌ریزی
- طراحی
- تحلیل
- مدل‌سازی
- اجرا
- بهره‌برداری
- تعمیر و نگهداری
- نرم‌افزار
- Web
- AI
- Data
- Automation
- پژوهش
- آموزش
- مشاوره
- محتوا
- GIS
- حمل‌ونقل
- عمران
- معدن
- صنعت
- کشاورزی
- گردشگری
- شهر هوشمند
- و سایر موارد

در UI مفهوم اصلی را:

> **مسئله / نیاز**

قرار بده و Project را فقط یکی از انواع درخواست در نظر بگیر.

---

## مسیر سوم — 🤝 همکاری با ما

برای فردی که:

- نمی‌خواهد دانشجو باشد
- فعلاً پروژه‌ای برای سپردن ندارد
- می‌خواهد با ما همکاری کند
- متخصص است
- پژوهشگر است
- برنامه‌نویس است
- تحلیل‌گر داده است
- طراح است
- مشاور است
- پیمانکار است
- می‌خواهد در پروژه‌ها عضو تیم شود
- می‌خواهد بعد از دوره دانشجویی همکاری خود را ادامه دهد

این مسیر در Homepage باید وجود داشته باشد، اما از نظر بصری نباید صفحه اول را شلوغ کند.

دو مسیر اصلی و برجسته:

### 📚 یادگیری و رشد

### 💼 طرح مسئله / نیاز

و در Header:

### 🤝 همکاری با ما

---

# 3. اصل معماری کلیدی: Person محور

هر فرد در سیستم یک شناسه دائمی دارد:

> **Person ID**

این شناسه هرگز با پایان یک ترم یا تغییر نقش عوض نمی‌شود.

یک فرد ممکن است در طول زمان نقش‌های مختلف داشته باشد:

```text
Person ID: P-00128

2026
Student

2027
Alumni

2027
Research Collaborator

2028
Project Contributor

2029
Client
```

بنابراین در طراحی اطلاعاتی از ابتدا:

> Person ≠ Student

و:

> Student یک Role است.

این اصل باید در معماری اطلاعات کاملاً دیده شود.

---

# 4. نگاه بلندمدت به محصول

محصول باید بتواند در آینده این اجزا را در خود جای دهد:

```text
Learning Platform
+
Research Platform
+
Project Management
+
Client Management
+
Collaboration Platform
+
Content Platform
+
Membership
+
AI Assistant
+
Second Brain
```

ولی در Homepage نباید این پیچیدگی را نشان بدهیم.

ظاهر عمومی باید ساده بماند.

---

# 5. Homepage

Homepage باید بسیار ساده، زیبا و حرفه‌ای باشد.

## Hero

عنوان:

> # یاد بگیر، مهارت بساز و خودت انجام بده؛ یا مسئله و نیازت را برای حل به ما بسپار.

زیرعنوان:

> آموزش، پژوهش، همکاری و توسعه راه‌حل‌های واقعی؛ از ایده تا اجرا.

دو CTA اصلی:

### 📚 یادگیری و رشد

### 💼 طرح مسئله / نیاز

CTA کوچک‌تر در Header:

### 🤝 همکاری با ما

---

# 6. Homepage باید هم برای دانشجو جذاب باشد و هم برای مشتری

این سایت نباید از همان ابتدا شبیه سایت آموزشی یا سایت خدماتی شود.

بلافاصله بعد از Hero چند نمونه از عمق سیستم را نشان بده.

مثلاً:

## یادگیری

- آموزش‌های تخصصی
- مطالب روزانه
- آزمون
- مسیر یادگیری
- مهارت‌ها

## پژوهش

- Dataset
- Research Problem
- Paper
- Analysis
- Q1-oriented Research

## حل مسئله

- Business
- Software
- AI
- Data
- Engineering
- Consulting
- Research

## همکاری

- Join Projects
- Research Collaboration
- Professional Collaboration

اما این‌ها را به‌صورت کارت‌های ساده و زیبا نمایش بده.

---

# 7. اثبات ارزش قبل از ثبت‌نام

کاربر باید قبل از ثبت‌نام بتواند ارزش واقعی سایت را ببیند.

Homepage باید بخش‌هایی مانند این داشته باشد:

### آخرین مطالب آموزشی

### پژوهش و داده

### نمونه پروژه‌ها

### Case Studies

### موضوعات تخصصی

### مسیرهای یادگیری

این محتوا نباید صرفاً تزئینی باشد.

کاربر باید بعد از چند دقیقه بتواند نتیجه بگیرد:

> «این سایت محتوای واقعی، تخصصی و قابل استفاده دارد.»

---

# 8. Content Strategy

محتوا یکی از ستون‌های اصلی محصول است.

در طول زمان محتوای تخصصی بسیار زیادی تولید خواهد شد.

به‌ویژه:

- مطالب آموزشی
- خلاصه مفاهیم کتاب‌ها
- مثال‌ها
- آموزش نرم‌افزار
- آموزش تحلیل داده
- AI در مهندسی
- پژوهش
- Dataset
- مقالات راهنما
- Case Study
- محتوای حاصل از تجربه پروژه‌ها

این محتوا باید از ابتدا **ماژولار** طراحی شود.

---

# 9. تأکید ویژه: Educational Module باید کاملاً Modular باشد

این بخش مهم‌ترین شرط طراحی است.

ماژول آموزش نباید با چند صفحه ثابت طراحی شود.

باید از ابتدا طوری Conceptualize شود که بتواند در آینده ده‌ها و صدها Course، Topic، Lesson، Article، Quiz، Dataset، Exercise و Learning Path را در خود جای دهد.

معماری مفهومی:

```text
Education
│
├── Courses
│   ├── Course
│   │   ├── Modules
│   │   │   ├── Topics
│   │   │   │   ├── Lessons
│   │   │   │   ├── Examples
│   │   │   │   ├── Exercises
│   │   │   │   ├── Quizzes
│   │   │   │   └── References
│
├── Learning Paths
│
├── Skill Library
│
├── Educational Articles
│
├── Question Bank
│
├── Assessments
│
└── Progress Analytics
```

این ساختار باید در طراحی UI نیز قابل مشاهده باشد.

---

# 10. Course Structure

برای هر Course، این اجزا را طراحی کن:

- Course Overview
- Modules
- Topics
- Lessons
- Daily Learning
- Quizzes
- Exercises
- References
- Progress
- Skills
- Projects

یک Course نباید صرفاً یک «صفحه درس» باشد.

باید شبیه یک Learning Environment واقعی باشد.

---

# 11. دانشجوی ترمی

دانشجوی ترمی هنگام ثبت‌نام:

```text
Registration
→ Select Semester
→ Select Course
→ Confirm
→ Student Dashboard
```

او باید بتواند:

- درس ترم خود را انتخاب کند
- آموزش‌های روزانه را دریافت کند
- آزمون دهد
- نمره بگیرد
- پروژه پژوهشی داشته باشد
- پروژه تجاری داشته باشد
- فرصت‌های پروژه را ببیند
- مهارت‌هایش را ببیند
- وضعیت کلی خودش را مشاهده کند

---

# 12. ساختار نمره دانشجو

سه ستون اصلی:

### Learning
40

### Research
40

### Commercial Project
40

و:

### Flexible / Bonus
20

در مجموع:

> 120 + 20 Flexible

در UI این را به شکل ساده و قابل فهم نمایش بده.

مثلاً:

```text
Learning        34 / 40
Research        31 / 40
Commercial      36 / 40
Flexible         8 / 20
```

فعلاً فرمول نهایی تبدیل به نمره رسمی را پیاده نکن.

فقط UI و مفهوم را طراحی کن.

---

# 13. Learning Dashboard دانشجو

یک Dashboard مدرن طراحی کن که نشان دهد:

- Today's Learning
- Quiz
- Weekly Progress
- Learning Score
- Topic Strength
- Topics Needing Attention
- Course Progress
- Streak
- Recent Activity

اما از شلوغی بیش از حد جلوگیری کن.

---

# 14. Daily Learning

هر روز دانشجو یک محتوای آموزشی کوتاه دریافت می‌کند.

مثلاً:

```text
Today's Learning
10 min

Topic:
Trip Generation

Read
→ Learn
→ Quiz
```

پس از مطالعه:

> Take Quiz

---

# 15. Quiz UI

آزمون‌ها:

- حدود 5 سؤال
- حدود 10 دقیقه
- حدود 2 دقیقه برای هر سؤال
- تستی / structured
- سؤال‌ها تصادفی
- گزینه‌ها تصادفی
- امکان Question Variant
- امکان پارامترهای عددی متفاوت
- یک سؤال در هر صفحه

در UI نمایش بده:

```text
Question 2 of 5

Time Remaining
01:34
```

و نتیجه بعد از آزمون:

```text
Score
4 / 5

Strength:
Flow Theory

Needs Review:
Trip Rate
```

در این مرحله فقط UI را طراحی کن.

---

# 16. Research Workspace

این بخش باید مستقل و بسیار جدی طراحی شود.

ساختار:

```text
Research
│
├── My Research Projects
├── Dataset Library
├── Research Problems
├── Benchmark Papers
├── Experiments
├── Results
├── Manuscript
└── Progress
```

---

# 17. Dataset Catalog

Dataset Catalog باید قابل توسعه برای تعداد زیادی Dataset باشد.

نمونه:

- NHTS
- NGSIM
- LTPP
- FARS
- HSIS
- Kaggle
- OSM
- Crash Data
- Weather Data
- Traffic Sensor Data
- Other Public Data

برای هر Dataset در UI حداقل این اطلاعات را نشان بده:

- Name
- Source
- Domain
- Geography
- Years
- Size
- Variables
- Format
- Research Topics
- Related Papers
- Typical Problems
- Difficulty
- License / Access

---

# 18. Research Problem Definition

دانشجو نباید فقط بگوید:

> «می‌خواهم مقاله بنویسم.»

باید یک Research Problem تعریف کند.

فرآیند UI:

```text
Select Dataset
→ Define Problem
→ Find Benchmark Paper
→ Read Paper
→ Identify Gap
→ Research Question
→ Method
→ Experiment
→ Results
→ Manuscript
```

در طراحی، مرحله تأیید استاد/مالک سیستم را نیز نمایش بده.

```text
Student Proposal
→ Instructor Review
→ Approved / Revision Required
```

---

# 19. Commercial Project Workspace

دانشجو باید یک بخش پروژه تجاری نیز داشته باشد.

پروژه ممکن است:

- توسط خود دانشجو تعریف شود
- توسط مشتری وارد شود
- توسط شما وارد شود
- از یک Lead خارجی آمده باشد
- از سازمان یا شرکت آمده باشد

ساختار:

```text
Commercial Projects
│
├── My Projects
├── Available Opportunities
├── Submitted Ideas
├── Active Work
├── Completed
└── Case Studies
```

---

# 20. Universal Problem / Need Intake

برای مشتری یا هر فرد عمومی یک صفحه اصلی داشته باش:

# مسئله یا نیاز خود را مطرح کنید

نه یک Landing Page جداگانه برای هر خدمت.

فرم ساده باشد.

ابتدا:

### نوع نیاز من

- Commercial
- Research
- Education
- Consulting
- Collaboration
- Other

سپس خدمات قابل انتخاب:

- Website / Web App
- AI
- Data Analysis
- Automation
- Content
- Research
- Engineering
- GIS
- Consulting
- Training
- Other

---

# 21. ذهن کاربر را با Example باز کن

بالای فرم یک بخش داشته باش:

## چه چیزی می‌توانید مطرح کنید؟

نمونه‌ها:

> «دانشجوی دکتری دانشگاه دیگری هستم و روی موضوع X کار می‌کنم.»

> «برای یک مقاله به تحلیل داده نیاز دارم.»

> «یک Dataset دارم و دنبال همکاری پژوهشی هستم.»

> «برای کسب‌وکارم به یک وب‌سایت یا Web App نیاز دارم.»

> «می‌خواهم فرآیند فروش و پیگیری مشتریانم Automation شود.»

> «می‌خواهم بدانم کدام بخش‌های کسب‌وکارم با AI قابل بهبود است.»

> «برای شرکت خود به Dashboard و تحلیل داده نیاز دارم.»

> «برای یک پروژه عمرانی به مطالعات، تحلیل یا طراحی نیاز دارم.»

> «یک ایده تجاری دارم و می‌خواهم آن را توسعه دهم.»

> «مورد من در این فهرست نیست و خودم آن را توضیح می‌دهم.»

این بخش باید از نظر بصری جذاب باشد و کاربر را برای تکمیل فرم راهنمایی کند.

---

# 22. فرم نباید پیچیده باشد

حدود 10 تا 20 سؤال کافی است.

سؤال‌ها:

1. چه کاری می‌خواهید انجام شود؟
2. مسئله اصلی چیست؟
3. نتیجه مورد انتظار چیست؟
4. نوع نیاز؟
5. حوزه فعالیت؟
6. آیا Data دارید؟
7. آیا Website لازم دارید؟
8. آیا AI لازم دارید؟
9. آیا Automation لازم دارید؟
10. آیا تحلیل داده لازم دارید؟
11. زمان مورد نظر؟
12. بودجه تقریبی؟
13. سازمان / شرکت
14. نام
15. شماره تماس
16. Email
17. توضیح تکمیلی

سؤال‌ها باید Dynamic باشند و همه را از ابتدا نشان نده.

---

# 23. Collaboration Page

صفحه جداگانه:

# 🤝 همکاری با ما

برای کسانی که می‌خواهند:

- در پروژه‌ها همکاری کنند
- پژوهش کنند
- متخصص شوند
- مشاور باشند
- عضو تیم شوند
- توسعه نرم‌افزار انجام دهند
- Data Science انجام دهند
- AI توسعه دهند
- روی پروژه‌های عمرانی و حمل‌ونقل کار کنند
- بعد از پایان تحصیل همکاری خود را ادامه دهند

فرم:

- معرفی
- تخصص
- مهارت‌ها
- سابقه
- علایق
- نوع همکاری
- ظرفیت زمانی
- نمونه‌کار
- رزومه
- اطلاعات تماس

---

# 24. Membership

از ابتدا Conceptual Membership را طراحی کن، حتی اگر فعلاً رایگان باشد.

مثلاً:

```text
Visitor
↓
Free Content
↓
Free Account
↓
Learner
↓
Premium / Professional Membership
```

اما فعلاً قیمت‌گذاری یا Payment را پیاده نکن.

هدف فقط این است که معماری UI قابلیت Membership آینده را داشته باشد.

---

# 25. محتوای رایگان و پولی

از نظر معماری مشخص کن که هر Content می‌تواند:

- Public
- Registered
- Member
- Student
- Premium

باشد.

این قابلیت باید مخصوصاً در Educational Module دیده شود.

---

# 26. Owner / Instructor Dashboard

یک Dashboard بسیار مهم برای مالک سیستم طراحی کن.

نمایش:

### Students

- Active
- Learning Progress
- Research Progress
- Commercial Progress

### Courses

- Courses
- Modules
- Topics
- Daily Content
- Question Bank

### Research

- Active Research
- Dataset Selection
- Pending Approvals
- Manuscripts

### Commercial

- Leads
- Requests
- Active Projects
- Opportunities
- Clients

### Collaboration

- Applicants
- Contributors
- Partners

### Content

- Drafts
- Published
- SEO
- Educational Library

### AI

- Recommendations
- Pending Approvals
- Alerts

---

# 27. AI-native بودن

سیستم از ابتدا باید برای اتصال AI طراحی شود.

در آینده AI باید بتواند بر اساس اطلاعات ساختاریافته پیشنهاد دهد:

- کدام دانشجو عقب است؟
- چه کسی امروز Quiz نداده؟
- چه کسی برای Project X مناسب است؟
- چه کسی در Research به مشکل خورده؟
- چه نمره‌ای پیشنهاد می‌شود؟
- چه مشتری‌هایی نیاز به Follow-up دارند؟
- چه پروژه‌هایی در Risk هستند؟
- چه محتوایی باید تولید شود؟
- چه Datasetی برای Research Problem مناسب است؟

اما:

> AI نباید بدون تأیید مالک، تصمیم‌های مهم را نهایی کند.

فرآیند:

```text
AI Recommendation
→ Human Review
→ Approve / Modify / Reject
→ Action
→ Audit Trail
```

---

# 28. Second Brain / Obsidian

در معماری آینده یک لایه Second Brain برای مالک در نظر بگیر.

ساختار مفهومی:

```text
00_Inbox
01_People
02_Students
03_Clients
04_Projects
05_Courses
06_Research
07_Datasets
08_Papers
09_Business
10_Meetings
11_Decisions
12_Content
13_Ideas
14_AI
99_Archive
```

این بخش فعلاً فقط Conceptual باشد.

هیچ Integration واقعی ایجاد نکن.

---

# 29. Public Content Strategy

سایت باید به‌مرور یک Knowledge Base بسیار بزرگ بسازد.

در آینده:

```text
Book
→ Concepts
→ Educational Notes
→ Examples
→ Quizzes
→ Student Feedback
→ Improved Content
→ SEO Article
```

این موتور محتوا باید از ابتدا Modular طراحی شود.

---

# 30. Important: Education Must Be the Most Extensible Module

در بین تمام بخش‌ها، بیشترین تأکید را روی قابلیت توسعه Module آموزش بگذار.

فرض کن در آینده:

- ده‌ها Course
- صدها Module
- هزاران Topic
- هزاران Lesson
- ده‌ها هزار Question
- صدها Dataset
- صدها Learning Path

داریم.

طراحی نباید نیازمند بازطراحی سیستم باشد.

بنابراین UI را بر اساس **Reusable Components** و **Nested Modular Structure** طراحی کن.

---

# 31. Navigation

## Public

```text
خانه
یادگیری
پژوهش
نمونه کارها
مطالب
درباره
ثبت مسئله / نیاز
همکاری
ورود
ثبت‌نام
```

## Learner

```text
داشبورد
یادگیری
دوره‌های من
آزمون‌ها
پژوهش
پروژه تجاری
فرصت‌های همکاری
مهارت‌ها
پروفایل
عضویت
```

## Client

```text
داشبورد
ثبت مسئله
درخواست‌های من
پروژه‌ها
پیام‌ها
اسناد
پروفایل
```

## Owner

```text
Dashboard
People
Students
Courses
Content
Quizzes
Research
Datasets
Projects
Leads
Clients
Collaboration
Grades
AI
Reports
Second Brain
```

---

# 32. یک اصل بسیار مهم در UX

کاربر نباید احساس کند:

> «وارد یک سیستم بسیار پیچیده شده‌ام.»

بلکه باید احساس کند:

> «می‌دانم برای چه آمده‌ام و فقط امکانات مربوط به خودم را می‌بینم.»

پس:

### Progressive Disclosure

را در کل محصول رعایت کن.

اطلاعات پیچیده را فقط وقتی لازم است نمایش بده.

---

# 33. Design Language

طراحی:

- Professional
- Modern
- Clean
- Academic
- Human
- Trustworthy
- Technology-oriented
- Minimal but rich

Avoid:

- ظاهر خشک دانشگاهی
- ظاهر بیش از حد Corporate
- ظاهر Marketplace ارزان
- Dashboardهای شلوغ
- انیمیشن‌های غیرضروری
- رنگ‌های زیاد
- UI شلوغ

RTL و Persian-first باشد.

---

# 34. Mobile-first Thinking

هر صفحه را طوری تصور کن که در موبایل نیز قابل استفاده باشد.

به‌خصوص:

- Learning
- Quiz
- Content
- Problem Intake
- Collaboration
- Student Dashboard

---

# 35. Screenهای مورد نیاز برای Prototype

حداقل این 20 صفحه را طراحی مفهومی کن:

1. Homepage
2. Learning Landing
3. General Content Library
4. Course Overview
5. Module View
6. Lesson View
7. Daily Learning
8. Quiz
9. Quiz Result
10. Learner Dashboard
11. Research Dashboard
12. Dataset Catalog
13. Research Problem Definition
14. Commercial Project Dashboard
15. Project Opportunities
16. Universal Problem / Need Intake
17. Collaboration Page
18. Client Dashboard
19. Owner Dashboard
20. Content Management

---

# 36. Homepage Prototype باید بسیار دقیق باشد

برای Homepage یک Mockup سطح بالا ارائه کن که نشان دهد:

### Header

Logo / Brand

Navigation

Login

CTA

### Hero

عنوان اصلی

Subheading

Two Primary CTA

### Content Preview

### Learning Preview

### Research Preview

### Project / Case Study Preview

### Collaboration Preview

### Final CTA

---

# 37. مهم‌ترین سؤال طراحی

در پایان خودت بررسی کن:

> آیا یک دانشجوی ترمی وقتی وارد Homepage می‌شود احساس می‌کند این سایت برای یادگیری و رشد او ساخته شده است؟

و هم‌زمان:

> آیا یک مدیر شرکت، پژوهشگر یا صاحب کسب‌وکار وقتی وارد Homepage می‌شود احساس می‌کند می‌تواند مسئله خود را مطرح کند؟

و:

> آیا یک متخصص وقتی وارد Homepage می‌شود می‌فهمد که می‌تواند برای همکاری وارد شود؟

اگر پاسخ به هر سه مثبت نیست، Design را اصلاح کن.

---

# 38. خروجی نهایی این مرحله

خروجی را دقیقاً در این ترتیب ارائه کن:

## 1. Product Vision

## 2. Core Principles

## 3. User Types

## 4. Person / Role Model

## 5. Information Architecture

## 6. Navigation

## 7. Homepage Concept

## 8. Learner Experience

## 9. Education Architecture

## 10. Research Experience

## 11. Commercial Project Experience

## 12. Universal Problem Intake

## 13. Collaboration Experience

## 14. Membership Concept

## 15. Content Architecture

## 16. Owner Dashboard

## 17. AI-Native Architecture

## 18. Obsidian / Second Brain Concept

## 19. Visual Design System

## 20. Full Screen-by-Screen Mockup Specification

## 21. Risks / Ambiguities

## 22. Recommended Changes

---

# 39. نحوه ارائه Prototype

برای هر Screen فقط این موارد را نشان بده:

- هدف صفحه
- ساختار صفحه
- عناصر اصلی
- Layout
- Hierarchy
- CTA
- Desktop
- Mobile
- تعاملات مفهومی

در این مرحله Implementation نکن.

---

# 40. توقف اجباری

بعد از تکمیل Design و Prototype:

> STOP.

هیچ کدی ننویس.

هیچ چیزی را اجرا نکن.

هیچ فایل پروژه را تغییر نده.

هیچ Commit نساز.

از من تأیید بگیر.

پس از تأیید من، وارد Phase 1 یعنی:

> Technical Architecture

خواهیم شد.

بعد از تأیید معماری فنی، وارد Phase 2 یعنی:

> Implementation

می‌شویم.

---

# اصل نهایی محصول

این محصول باید در نهایت بتواند یک چرخه کامل بسازد:

```text
CONTENT
   ↓
LEARNING
   ↓
SKILL
   ↓
RESEARCH / PROJECT
   ↓
REAL-WORLD EXPERIENCE
   ↓
COLLABORATION
   ↓
CLIENT
   ↓
PROJECT
   ↓
CASE STUDY
   ↓
NEW CONTENT
   ↓
NEW USERS
```

و هدف نهایی این است که:

> **سایت فقط محلی برای ارائه محتوا یا مدیریت دانشجو نباشد؛ بلکه به‌مرور به یک سیستم زنده برای یادگیری، پژوهش، همکاری، جذب مسئله، اجرای پروژه و توسعه کسب‌وکار تبدیل شود.**

در این مرحله فقط **پوسته و تجربه کاربری** را طراحی کن.

**هیچ کدی ننویس.**
