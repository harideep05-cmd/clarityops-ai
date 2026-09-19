# Five-minute demo

Prerequisites: root README setup complete, prepared embedding files, workspace token,
and a valid Gemini key for genuine generated answers. Do not use the browser test server
as a customer-facing demonstration of Gemini quality.

1. Open http://127.0.0.1:5173 and unlock with the workspace token.
2. Upload `samples/Meridian_Works_Handbook.pdf`. It should show five pages and Ready.
3. Ask: **How many casual leave days do employees receive per calendar year?**
   Expected policy: 12, on physical page 1. Check the exact quotation beneath the answer.
4. Ask: **When is the deadline for submitting receipts for reimbursement?**
   Expected policy: 14 calendar days, on page 2.
5. Ask: **My company laptop is lost. What should I do?**
   Expected evidence: report immediately to the IT service desk; include asset tag and
   last known location, page 4.
6. Ask: **How many parental leave days do employees receive?**
   That policy is absent. Expect an explicit insufficient-evidence answer, with no sources.
7. Re-upload the same file. It should be deduplicated with no second document entry.
8. Download a source, verify its physical page, then remove the document and confirm it
   disappears. Questions cannot use the removed index. A downloaded copy remains yours.

If the key is missing, demonstrate local indexing and the controlled setup error,
then stop: do not claim that generated answers were demonstrated. If the provider
fails, the UI should show a retryable service error, not a fabricated answer.

The sample represents a fictional company. No real employment policies are asserted.
