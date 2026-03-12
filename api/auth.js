export default async function handler(req, res) {
  const { code } = req.query;
  const client_id = process.env.GITHUB_CLIENT_ID;
  const client_secret = process.env.GITHUB_CLIENT_SECRET;

  try {
    const response = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
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

    // הקוד הזה מחזיר את ה"מפתח" למערכת הניהול שלך בדפדפן
    res.send(`
      <script>
        const content = {
          token: "${data.access_token}",
          provider: "github"
        };
        window.opener.postMessage(
          "authorizing:github:" + JSON.stringify(content),
          window.location.origin
        );
      </script>
    `);
  } catch (error) {
    res.status(500).send("Internal Server Error");
  }
}
