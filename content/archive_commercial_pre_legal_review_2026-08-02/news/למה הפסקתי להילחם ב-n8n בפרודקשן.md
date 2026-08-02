---
title: >-
  למה הפסקתי להילחם ב-n8n בפרודקשן?
date: "2026-07-09 13:37:35"
source: "Geektime"
image: "https://cdn.geektime.co.il/wp-content/uploads/2026/07/TEMPORAL.jpg"
link: "https://www.geektime.co.il/coding-temporal-n8n/"
category: "טכנולוגיה"
---

עברתי מ-n8n ל-Temporal כדי לנהל פייפליין וידאו מבוסס AI, וחזרתי עם כמה מסקנות ותובנות

כלי אוטומציה כמו n8n, make, zapier ודומיהם הפכו פופולריים כיום עוד יותר מבעבר בזכות מהפכת ה-AI, אבל המקום שלהם עכשיו לא ברור. בעולם שנשלט על ידי coding agents כמו Claude Code, אותם החסמים שפלטפורמות low-code תוכננו לעקוף, נפתרים ברמת כתיבת הקוד. היתרון של אינטרפייס ויזואלי עם drag & drop כבר לא חד משמעי על פני שיחה עם קלוד, ובנוסף לכך, הוא מביא איתו את החסרונות והמגבלות הקיימים.

כיועץ ובונה של מערכות AI לפרודקשן, אני רואה את הדילמה הזו חוזרת בארגונים רבים עם מוצר שמתחיל להבשיל מ-POC ורעיון של מפתח למוצר של ממש, שמשרת את הלקוחות של הארגון או אפילו מוצר פנימי.

במאמר הזה אפרט את הנימוקים מאחורי מיגרציה מ-n8n בפרויקט בתחום הווידאו, ספציפית פייפליין דטרמיניסטי של AI Video. ניגע בסיבות הטכניות, הביזנסיות וכל מה שביניהן. חשוב לציין שאני מדבר כאן על השימוש בגרסאות החינמיות בקוד פתוח של n8n ושל Temporal כאשר עלויות הענן והתשתית בניהול עצמי הן על הארגון.

ככל שהפרויקט הבשיל והמורכבות גדלה, המגבלות הארכיטקטוניות הבסיסיות של n8n נעשו ברורות יותר. היעדר תמיכה מובנית ב-durability אילץ אותנו ליצור workarounds, ובניית workflows לא הוכיחה את עצמה כמהירה יותר מכתיבת קוד בעידן של היום, מה שלמעשה ביטל את רוב היתרונות הראשוניים של n8n. המערכת הפכה ליקרה לתחזוקה, קשה מאוד לדיבוג, ורחוקה מסטנדרטים מודרניים של פיתוח תוכנה. בסופו של דבר, אותם חסרונות של הפלטפורמה הפכו אותה לבסיס לא מתאים למוצר פרודקשן בסקייל שמשרת אפילו עשרות יוזרים, ועל אחת כמה וכמה בעידן של coding agents.

קיבלנו החלטה לנטוש את n8n ולהחליף אותו בפריימוורק אופן סורס בשם Temporal. המודל הבסיסי של Temporal שונה מהותית מזה של n8n. הוא Code-First, תומך ב-Durable Execution ומגיע out of the box עם עמידות בעומסים. The headless n8n אם תרצו.

כל workflow הוא בעצם סדרה של שורות קוד עם await, כל שורת קוד כזאת היא בעצם פונקציה שרצה ב-worker משלה שנקראת Activity – סוג של המקבילה ל-Custom Code Node ב-n8n. לוגיקה פשוטה כמו if/else ו-loops הם פשוט קוד בתוך ה-workflow ולא nodes בפני עצמם.

ב-n8n, ה-workflow מתחיל, רץ עד הסוף, ומת. אם הוא קורס, ההתקדמות אובדת, אלא אם כן נבנה checkpointing ידני/חיצוני. ב-Temporal, כל הרצה של workflow נשמרת כרצף של אירועים. כל await הוא checkpoint; אם ה-worker קורס, Temporal משחזר וממשיך את ההרצה בדיוק מהנקודה בה נעצרה. אין timeout על הרצות, אין state ידני ואין דטבייס שצריך לתחזק.

כדי להמחיש עד כמה גישת code-first מפשטת את הפייפליין, שווה להסתכל על איך workflow של יצירת הווידאו היה נראה בפועל. כמו שהזכרתי למעלה, היעדר תמיכה מובנית ב-durability דחף את הארכיטקטורה לכיוון של workflows עצמאיים לחלוטין.

workflow ב-n8n היה מורכב מחמישה שלבים נפרדים שעושים polling אל מול ה-state:

workflows לא מודעים אחד לשני וה-state הוא ה-source of truth.

הדרך שעובר וידאו בודד, מבקשה ועד השלמה, היא דרך כל חמשת ה-workflows, כשהמעקב מתבצע לחלוטין דרך מעברי שדה סטטוס:

pending → image_pending → image_generating → image_done → video_rendering → video_done → stitching → complete

כל שלב עושה retry לקריאות שנכשלו במחזור ה-polling הבא.

הבעיה היא שה-overhead המצטבר של תחזוקת מערכת אורקסטרציה שנבנתה ידנית, עולה על המורכבות של המוצר עצמו. הפייפליין הוא הליבה של המוצר, ויותר שעות פיתוח מושקעות ב-scaffolding שלו מאשר ב-business logic.

באופן אירוני, הארכיטקטורה הזו גם מחסלת את אחת מנקודות המכירה של n8n, מעקב ויזואלי אחרי ה-workflow. כבר אי אפשר לעקוב בקלות אחר הדרך שעובר וידאו בודד ב-canvas אחד, הוא מפוזר על פני חמישה workflows מנותקים, כשהדטבייס הוא החוט המחבר היחיד ביניהם.

export async function cloneVideoWorkflow(input: CloneVideoInput): Promise<void> { const analysis = await analyzeVideo(input.videoUrl); // Fan-out: all scenes generate images in parallel across workers const images = await Promise.all( analysis.scenes.map(scene => generateImage({ prompt: scene.imagePrompt, referenceImage: input.characterSheetUrl, })) ); // Fan-out again: all scenes generate videos in parallel const videos = await Promise.all( images.map((img, i) => generateVideo({ imageUrl: img.url, prompt: analysis.scenes[i].videoPrompt, duration: analysis.scenes[i].duration, })) ); // Fan-in: stitch only runs when ALL scenes are complete await stitchVideos({ scenes: videos, contentItemId: input.contentItemId }); } חמישה workflows, מעל 30 nodes, ו-state machine בדטבייס עם 8 סטטוסים שונים, מתכווצים ל-15 שורות TypeScript. כל activity רץ על worker משלו עם retries אוטומטיים.

אם יצירת הווידאו של סצנה 3 נכשלת, רק סצנה 3 עושה retry. אם worker קורס, ההרצה ממשיכה מה-checkpoint האחרון. בלי polling, בלי שדות סטטוס, בלי שחזור ידני.

קוד אמיתי, כלים אמיתיים, תשתית אמיתית

ה-workflows של Temporal הם קבצי TypeScript ב-Git. הם עוברים code review ב-pull request, יש להם unit tests, והם עולים לפרודקשן דרך ה-pipeline הרגיל של CI/CD. כל שינוי מקושר ל-commit עם rollback. בתוך activities, אפשר להשתמש בכל SDK או כלי פיתוח: Vercel AI SDK לקריאות LLM, ‏Drizzle לתקשורת עם הדטבייס, Zod לסכמה, שליטה מלאה על עיבוד המדיה עם ספריות מוכחות כמו Sharp/FFmpeg ובעצם כל מה שאנחנו לוקחים בכתיבת קוד כמובן מאליו. בלי nodes גנריים, בלי קריאות API ב-vanilla JavaScript.

תהליך הפיתוח הוא מודרני לגמרי עם Claude באופן טבעי – כי מדובר פשוט בקוד מבחינתו.

ב-n8n, כשרצינו סוגי וידאו חדשים, כל שלב היה צריך לתמוך בהסתעפות על בסיס סוג הווידאו שנשמר בסטייט, או לשכפל את כל סט ה-workflows ולשנות אותם. שתי הגישות פוגעות בסקייל ובמודולריות. בקוד, לכל שלב אפשר לעשות reuse – הוא פשוט פונקציה שמיוצאת ממודול משותף.

activity של generateImage מיובא ונקרא מתוך ה-clone video workflow, ה-UGC workflow, וה-promotional workflow. בדיקת type-safety מלאה של TypeScript על inputs ו-outputs. אם האינטרפייס של ה-activity משתנה, כל מי שקורא לו מקבל שגיאה בקומפייל. ולא שגיאה ב-runtime שמגלים בפרודקשן שלושה ימים אחר כך.

היתרון שבדשבורד ניהול כבר לא משמעותי

האינטרפייס הוויזואלי של n8n, שמאפשר לאנשים שאינם טכניים להפעיל workflows, לעקוב אחרי סטטוס, ולראות אילו אוטומציות קיימות, הופך לפחות משמעותי בעולם שכל הקוד נכתב באמצעות coding agents ואפשר ליצור ממשקים באותה מהירות שכותבים workflows ב-Temporal. מה גם ש-frontend מותאם אישית לא רק נוצר מהר יותר מהצפוי, הוא גם טוב יותר: מותאם בדיוק ל-use case ולא מוגבל בממשק של עורך workflows גנרי.

Durable Execution מייתר את ה-State Machine

ב-Temporal, כל ה-overhead של ניהול state בדטבייס נעלם. Temporal היא שכבת אורקסטרציה שבנויה בדיוק למטרה הזו ומוכחת בשטח. כל סוג workflow חדש מתחיל נקי: מגדירים את השלבים, מגדירים את ה-activities, עושים deploy. במיוחד בארגונים, שמטבע הדברים מריצים מאות ואלפי קריאות ביום, durable execution הופך מ-nice to have לחובה. כל ה-side effects (קריאות API, כתיבות לדטבייס, פעולות על קבצים) חיים ב-Activities, בעוד ה-Workflow נשאר קואורדינטור דטרמיניסטי. זה מאפשר replays של שלבים, unit tests ועוד.

לכל activity יש retry policy משלו עם exponential backoff. שגיאות זמניות (בעיות רשת, API timeouts) מטופלות אוטומטית. שגיאות יותר קריטיות צפות מיד עם כל הקונטקסט. אין יותר ghost errors בדטבייס.

ה-polling בכל שלב של n8n הופך ל-Promise.all אחד. 100 סרטונים זה 100 instances עצמאיים של workflow שרצים במקביל על פני workers נפרדים, כל אחד עם ה-state משלו והיסטוריית ה-retry שלו. כשאחד נכשל הוא לא משפיע על ה-99 האחרים.

כל activity נכנס ל-task queue; ה-workers שולפים עבודה בקצב שלהם, מה שמספק backpressure טבעי שחסר לגמרי ב-n8n.

ל-Temporal יש UI וובי שמאפשר לקבל נתונים ב-realtime על ריצות וגם את כל ההיסטוריה. כשמשהו נכשל, אפשר לראות בדיוק איזה activity נכשל, מה היה ה-input, מה הייתה הודעת השגיאה, כמה פעמים הוא ניסה שוב, ומה היה ה-state הסופי. אפשר לעשות replay ל-workflows, לאפס מכל נקודה בהיסטוריה, או לסיים אותם. הדיבוג של ה-workflows עבר מחפירה בתוך לוגים מ-5 נקודות לסינכרון ריצות, ללחיצה פשוטה על ה-workflow ID וקריאת ה-timeline.

באמצעות Temporal Signals אפשר לתקשר ב-realtime עם workflows רצים: לעצור יצירת סרטון באמצע, לבטל, לשנות עדיפות, או לבדוק התקדמות.

Temporal מגיע גם עם CLI ו-MCP משלו, ככה שאפשר לנטר ולתקן את השגיאות בצורה יעילה ישירות מקלוד.

Temporal מטפל ב-task routing, חלוקת עומסים, deduplication, וניהול state. הסקיילינג הרבה יותר גרנולרי, פר activity ולא פר workflow. ניתן לקנפג worker pools ייעודיים למטרות שונות: pool כללי, pool עם concurrency נמוך לכתיבות לדטבייס (כדי למנוע deadlocks מפעולות מקבילות), ו-pool ייעודי ליצירת סרטונים ממושכת. בניגוד ל-n8n שיש בו בעצם pool אחד לכל ה-workflows.

ב-polling שלנו ב-n8n, החלוקה ל-workers תלויה במרווחי זמן של כל poll. ה-task queues של Temporal הם event-driven שנשלחים מיד וה-workers שולפים בקצב שלהם, מה שמספק backpressure טבעי.

מאז המעבר ל-Temporal, אנחנו סוף סוף חווים את מה שחשבנו ש-n8n יספק: במהירות הפיתוח ובסקייל. הפלטפורמה משרתת לקוחות שכל אחד מהם מייצר בממוצע כ-6 סרטונים ביום, כשכל סרטון מכיל 4-6 סצנות שדורשות יצירת תמונה וסרטון לכל סצנה. גם בסקייל צנוע (נניח 50 לקוחות), מדובר ב-300 סרטונים ומעל 1,500 ג'ינרוטים בודדים ביום.

לכלי אוטומציה low-code יש עדיין מקום. n8n הוא עדיין בחירה טובה לדמואים, פרוטוטייפים, טסטים ואוטומציות פנימיות/פרטיות. אבל למערכות שדורשות durability, סקייל, ומודולריות – יש אי התאמה שמצטברת בעלות לאורך זמן.

הלקח העמוק מהמיגרציה הזו לא היה רק "Temporal טוב יותר מ-n8n" הלקח הוא ההבנה שחודשים הושקעו בבניית תשתיות מורכבות יותר ויותר כדי לעבוד סביב כלי שלא מתאים מיסודו, גם לא לשלב ה-MVP. ברגע שהדרישות הפכו לקצת יותר מבסיסיות, המערכת הפכה לגרסה גרועה יותר של מה ש-Temporal מספק out of the box. בעידן של AI coding agents, הלקח ברור: קוד הוא כיום הדרך עם הכי פחות חיכוך. המחסומים שה-low-code תוכנן לעקוף כבר לא קיימים כש-LLM יכול לייצר קוד תוך שניות.

יוחאי רוזן הוא יועץ ומומחה AI שמלווה ארגונים בבניית תשתיות ומערכות AI לפרודקשן

[קרא את הכתבה המלאה במקור](https://www.geektime.co.il/coding-temporal-n8n/)
