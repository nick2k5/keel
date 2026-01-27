const CONFIG = {
  agentEmail: 'keel@friale.com',
  endpoint: 'https://keel-memo-generator-952407610436.us-central1.run.app/email'
};

function checkForTriggerEmails() {
  const threads = GmailApp.search('is:unread', 0, 10);

  if (threads.length === 0) return;

  threads.forEach(thread => {
    const messages = thread.getMessages();
    const latestMessage = messages[messages.length - 1];

    // Skip if we sent the last message (avoid loops)
    if (latestMessage.getFrom().includes(CONFIG.agentEmail)) {
      return;
    }

    // Build email data
    const emailData = {
      from: latestMessage.getFrom(),
      to: latestMessage.getTo(),
      subject: latestMessage.getSubject(),
      body: latestMessage.getPlainBody()
    };

    Logger.log(`Processing: "${emailData.subject}" from ${emailData.from}`);

    // Send to Cloud Run endpoint
    const response = UrlFetchApp.fetch(CONFIG.endpoint, {
      method: 'POST',
      contentType: 'application/json',
      payload: JSON.stringify(emailData),
      muteHttpExceptions: true
    });

    const result = JSON.parse(response.getContentText());
    Logger.log(`Response: ${JSON.stringify(result)}`);

    // Reply with the response text
    const replyText = result.reply_text || 'Sorry, something went wrong.';
    thread.reply(replyText);

    // Mark as read
    thread.markRead();

    Logger.log('Replied and marked as read');
    thread.moveToArchive();
  });
}

function testEndpoint() {
  const testEmail = {
    from: 'test@example.com',
    subject: 'Add company',
    body: 'stripe.com'
  };

  const response = UrlFetchApp.fetch(CONFIG.endpoint, {
    method: 'POST',
    contentType: 'application/json',
    payload: JSON.stringify(testEmail),
    muteHttpExceptions: true
  });

  Logger.log(response.getContentText());
}
