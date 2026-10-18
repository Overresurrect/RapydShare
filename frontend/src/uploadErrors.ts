// The server's upload errors are generic, so the wording is chosen here by status.
const MESSAGES: Record<number, string> = {
    400: 'The upload was interrupted',
    401: 'Enter the access code again',
    403: 'Uploads are turned off',
    411: 'The upload could not start',
    413: 'File is too large',
    500: 'The computer could not save the file',
    503: 'Upload folder is not available',
    507: 'Not enough space on the computer',
};

export function uploadErrorMessage(status: number): string {
    return MESSAGES[status] ?? `Error ${status}`;
}
