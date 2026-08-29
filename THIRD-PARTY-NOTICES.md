# Third-party notices

The `fitfast` binary wheel statically links the following third-party Rust
crates. Their licenses are reproduced or referenced below as required.

## rustyfit

All FIT decoding in this package is performed by the
[rustyfit](https://github.com/muktihari/rustyfit) crate
([crates.io](https://crates.io/crates/rustyfit)).

> BSD 3-Clause License
>
> Copyright (c) 2025, Hikmatulloh Hari Mukti
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this
>    list of conditions and the following disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its
>    contributors may be used to endorse or promote products derived from
>    this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
> FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
> DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
> SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
> CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
> OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
> OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

rustyfit's own documentation notes that the FIT Protocol and FIT file format
are proprietary to Garmin and that use may require compliance with the
[FIT Protocol License](https://www.thisisant.com/developer/ant/licensing/flexible-and-interoperable-data-transfer-fit-protocol-license).
`fitfast` does not redistribute the Garmin FIT SDK, its `Profile.xlsx`, or any
files covered by the FIT SDK license.

## PyO3 and rust-numpy

The bindings are built with [PyO3](https://github.com/PyO3/pyo3) and
[rust-numpy](https://github.com/PyO3/rust-numpy), both dual-licensed under
MIT OR Apache-2.0. This distribution uses them under the MIT license:
<https://github.com/PyO3/pyo3/blob/main/LICENSE-MIT>,
<https://github.com/PyO3/rust-numpy/blob/main/LICENSE>.

This project is not affiliated with or endorsed by Garmin.
