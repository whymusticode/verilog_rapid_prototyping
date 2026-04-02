library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity Address_Generator is
    Port ( CLK25       : in  STD_LOGIC;
           rez_160x120 : in  STD_LOGIC;
           rez_320x240 : in  STD_LOGIC;
           enable      : in  STD_LOGIC;
           vsync       : in  STD_LOGIC;
           address     : out STD_LOGIC_VECTOR(18 downto 0));
end Address_Generator;

architecture Behavioral of Address_Generator is
    signal addr : unsigned(18 downto 0) := (others => '0');
    signal x_pix : unsigned(9 downto 0) := (others => '0'); -- 0..639
    signal y_pix : unsigned(8 downto 0) := (others => '0'); -- 0..479
    signal enable_prev : std_logic := '0';
begin
    address <= std_logic_vector(addr);

    process(CLK25)
    begin
        if rising_edge(CLK25) then
            if vsync = '0' then
                addr <= (others => '0');
                x_pix <= (others => '0');
                y_pix <= (others => '0');
                enable_prev <= '0';
            else
                if enable = '1' then
                    if enable_prev = '0' then
                        x_pix <= (others => '0');
                    elsif x_pix = to_unsigned(639, x_pix'length) then
                        x_pix <= (others => '0');
                    else
                        x_pix <= x_pix + 1;
                    end if;
                elsif enable_prev = '1' then
                    if y_pix = to_unsigned(479, y_pix'length) then
                        y_pix <= (others => '0');
                    else
                        y_pix <= y_pix + 1;
                    end if;
                end if;

                -- 320x240 framebuffer addressed from 640x480 scan (2x upscale)
                addr <= (resize(y_pix(8 downto 1), 19) sll 8) +
                        (resize(y_pix(8 downto 1), 19) sll 6) +
                        resize(x_pix(9 downto 1), 19); -- y*320 + x

                enable_prev <= enable;
            end if;
        end if;
    end process;

end Behavioral;
