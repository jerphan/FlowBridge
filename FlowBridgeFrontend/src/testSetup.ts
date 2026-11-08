import {afterEach} from 'vitest';
import {cleanup} from '@testing-library/react';

afterEach(cleanup);

// jsdom needs dialog methods; the browser tests exercise native showModal/close.
HTMLDialogElement.prototype.showModal = function () {this.setAttribute('open', '');};
HTMLDialogElement.prototype.close = function () {this.removeAttribute('open');};
