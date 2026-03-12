export default async function handler(req, res) {
  const { code } = req.query;
  
  // המשתנים האלו חייבים להיות מוגדרים ב-Vercel Dashboard
  const client_id = process.env.GITHUB_CLIENT_ID;
  const client_secret = process.env.GITHUB_CLIENT_SECRET;

  if (!code) {
    return res.status(400).json({ error: 'No code provided' });
  }

  try {
    const response = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({
        client_id,
        client_secret,
        code,
      }),
    });

    const data = await response.json();

    if (data.error) {
      return res.status(400).send(`Error: ${data.error_description}`);
    }

    // זה החלק שמעביר את הטוקן חזרה ל-Decap CMS שפתוח בדפדפן
    res.setHeader('Content-Type', 'text/html');
    return res.send(`
      <!DOCTYPE html>
      <html>
        <body>
          <script>
            (function() {
              function receiveMessage(e) {
                if (e.origin !== window.location.origin) return;
                
                window.opener.postMessage(
                  'authorizing:github:{"token":"${data.access_token}","provider":"github"}',
                  e.origin
                );
              }
              window.addEventListener("message", receiveMessage, false);
              window.opener.postMessage("authorizing:github", window.location.origin);
            })()
          </script>
        </body>
      </html>
    `);
  } catch (error) {
    console.error(error);
    return res.status(500).send("Internal Server Error");
  }
}
