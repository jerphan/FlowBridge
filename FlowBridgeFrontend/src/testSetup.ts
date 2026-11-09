import {afterEach, vi} from 'vitest';
import {cleanup} from '@testing-library/react';

afterEach(cleanup);
HTMLElement.prototype.scrollTo = vi.fn();
HTMLElement.prototype.scrollBy = vi.fn();

// jsdom needs dialog methods; the browser tests exercise native showModal/close.
HTMLDialogElement.prototype.showModal = function () {this.setAttribute('open', '');};
HTMLDialogElement.prototype.close = function () {this.removeAttribute('open');};
