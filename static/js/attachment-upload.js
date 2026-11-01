/* Disables the upload submit button and swaps its label for a progress bar while the
 * form POSTs - same loading pattern as SaldoVibe's attachments/attachment_list.html.
 * The upload can take several seconds since ReInvGrabber's OCR extraction runs
 * synchronously as part of the request (see attachments/services.py::save_attachment_with_thumbnail),
 * so without this a double-click re-submits the file and creates a duplicate attachment.
 */
window.ExpenseVibe = window.ExpenseVibe || {};

(function (namespace) {
  'use strict';

  function resolveElement(value) {
    return typeof value === 'string' ? document.getElementById(value) : value;
  }

  function initUploadLoadingState(options) {
    var opts = options || {};
    var form = resolveElement(opts.form);
    var submitBtn = resolveElement(opts.submitBtn);
    var label = resolveElement(opts.label);
    var loading = resolveElement(opts.loading);
    var progress = resolveElement(opts.progress);
    if (!form || !submitBtn || !label || !loading) {
      return;
    }

    form.addEventListener('submit', function () {
      label.classList.add('d-none');
      loading.classList.remove('d-none');
      if (progress) {
        progress.classList.remove('d-none');
      }
      // Disabling the submit button synchronously in the submit handler cancels the
      // submission in Safari, so defer it until after the browser has started
      // processing the form post.
      window.setTimeout(function () { submitBtn.disabled = true; }, 0);
    });
  }

  namespace.attachments = {
    initUploadLoadingState: initUploadLoadingState
  };
})(window.ExpenseVibe);
