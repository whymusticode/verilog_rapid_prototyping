library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity ov7670_capture is
    Port ( pclk        : in  STD_LOGIC;
           rez_160x120 : in  STD_LOGIC;
           rez_320x240 : in  STD_LOGIC;
           vsync       : in  STD_LOGIC;
           href        : in  STD_LOGIC;
           d           : in  STD_LOGIC_VECTOR(7 downto 0);
           addr        : out STD_LOGIC_VECTOR(18 downto 0);
           dout        : out STD_LOGIC_VECTOR(11 downto 0);
           we          : out STD_LOGIC);
end ov7670_capture;

architecture Behavioral of ov7670_capture is
    signal d_hi       : std_logic_vector(7 downto 0) := (others => '0');
    signal address_u  : unsigned(18 downto 0) := (others => '0');
    signal href_prev  : std_logic := '0';
    signal byte_phase : std_logic := '0';
    signal x_pix      : unsigned(9 downto 0) := (others => '0'); -- 0..639
    signal y_pix      : unsigned(8 downto 0) := (others => '0'); -- 0..479
begin
    addr <= std_logic_vector(address_u);

    process(pclk)
    begin
        if rising_edge(pclk) then
            we <= '0';

            if vsync = '1' then
                address_u <= (others => '0');
                x_pix <= (others => '0');
                y_pix <= (others => '0');
                byte_phase <= '0';
                href_prev <= '0';
            else
                if href = '1' then
                    if byte_phase = '0' then
                        d_hi <= d;
                        byte_phase <= '1';
                    else
                        -- RGB565 -> RGB444
                        dout <= d_hi(7 downto 4) & d_hi(2 downto 0) & d(7) & d(4 downto 1);

                        -- 640x480 camera -> 320x240 framebuffer: keep one pixel per 2x2 block
                        if x_pix(0) = '0' and y_pix(0) = '0' then
                            address_u <= (resize(y_pix(8 downto 1), 19) sll 8) +
                                         (resize(y_pix(8 downto 1), 19) sll 6) +
                                         resize(x_pix(9 downto 1), 19); -- y*320 + x
                            we <= '1';
                        end if;

                        if x_pix = to_unsigned(639, x_pix'length) then
                            x_pix <= (others => '0');
                        else
                            x_pix <= x_pix + 1;
                        end if;

                        byte_phase <= '0';
                    end if;
                else
                    byte_phase <= '0';
                    if href_prev = '1' then
                        x_pix <= (others => '0');
                        if y_pix = to_unsigned(479, y_pix'length) then
                            y_pix <= (others => '0');
                        else
                            y_pix <= y_pix + 1;
                        end if;
                    end if;
                end if;

                href_prev <= href;
            end if;
        end if;
    end process;

end Behavioral;
