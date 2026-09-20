export async function api(path, token, options = {}) {
  const { download, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 75000);
  try {
    const response = await fetch(`/api${path}`, {
      ...fetchOptions,
      headers: { "X-ClarityOps-Token": token, ...options.headers },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const reference = response.status >= 500 && data.error?.request_id
        ? ` (Reference: ${data.error.request_id})` : "";
      const error = new Error((data.error?.message || `Request failed (${response.status}). Please retry.`) + reference);
      error.status = response.status;
      error.code = data.error?.code;
      throw error;
    }
    if (response.status === 204) return null;
    if (download) return await response.blob();
    return await response.json();
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "This request timed out. Please retry. Your document list will show any completed upload.",
        { cause: error },
      );
    if (error instanceof TypeError)
      throw new Error(
        "Could not reach ClarityOps. Check that the backend is running and retry.",
        { cause: error },
      );
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export async function downloadDocument(source, token) {
  const blob = await api(`/documents/${source.document_id}/file`, token, {
    download: true,
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = source.document;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
